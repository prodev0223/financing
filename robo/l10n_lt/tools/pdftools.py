# -*- coding: utf-8 -*-
import hashlib
import os
from io import BytesIO
from lxml import etree, objectify
from tempfile import NamedTemporaryFile
from datetime import datetime
from PyPDF4 import PdfFileWriter, PdfFileReader
from PyPDF4.generic import DictionaryObject, DecodedStreamObject, \
    NameObject, createStringObject, ArrayObject, IndirectObject
from PyPDF4.utils import b_
from odoo import _, exceptions

import logging

logger = logging.getLogger(__name__)

XML_FILENAME = 'e-invoice.xml'
LT_E_INVOICE_XSD_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../sepa/', 'xsd_schemas')) + '/eInvoice-1.1-LT.xsd'


def validate_xsd(xml_str, flavor='esaskaita'):
    """
    Validate the provided XML against Estonian e-invoice XSD
    :param: xml_str: XML to validate, as a str
    :param: flavor: XSD style
    :return: (True/False, error_msg)
    """
    if flavor == 'esaskaita':
        xsd_file = LT_E_INVOICE_XSD_PATH
    else:
        raise NotImplementedError(_('Šiuo metu palaikomas tik lietuviškos e-sąskaitos formatas'))
    try:
        schema = etree.XMLSchema(file=xsd_file)
        parser = objectify.makeparser(schema=schema)
        objectify.fromstring(xml_str, parser)
        return True, str()
    except Exception as exc:
        return False, exc.args[0]


def _get_pdf_timestamp(date=None):
    """ Returns a timestamp in expected date format for PDF data """
    if date is None:
        date = datetime.now()
    # example date format: "D:20141006161354+02'00'"
    pdf_date = date.strftime("D:%Y%m%d%H%M%S+00'00'")
    return pdf_date


def _get_metadata_timestamp():
    """ Returns a timestamp in expected date format (ISO6081) for metdata """
    return datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S+00:00')


def _get_dict_entry(node, entry):
    if not isinstance(node, dict):
        raise ValueError('The node must be a dict')
    dict_entry = node.get(entry)
    if isinstance(dict_entry, dict):
        return dict_entry
    elif isinstance(dict_entry, IndirectObject):
        res_dict_entry = dict_entry.getObject()
        if isinstance(res_dict_entry, dict):
            return res_dict_entry
        else:
            return False
    else:
        return False


def pdf_update_metadata_add_attachment(pdf_filestream, xml_content, pdf_metadata,
                                       output_intents=[]):
    """
    This method is inspired from the code of the addAttachment()
    method of the PyPDF2 lib'
    :param pdf_filestream:
    :param xml_content:
    :param pdf_metadata:
    :param output_intents:
    :return:
    """
    md5sum = hashlib.md5(xml_content).hexdigest()
    md5sum_obj = createStringObject(md5sum)
    params_dict = DictionaryObject({
        NameObject('/CheckSum'): md5sum_obj,
        NameObject('/ModDate'): createStringObject(_get_pdf_timestamp()),
        NameObject('/Size'): NameObject(str(len(xml_content))),
    })
    file_entry = DecodedStreamObject()
    file_entry.setData(xml_content)  # here we integrate the file itself
    file_entry.update({
        NameObject("/Type"): NameObject("/EmbeddedFile"),
        NameObject("/Params"): params_dict,
        # 2F is '/' in hexadecimal
        NameObject("/Subtype"): NameObject("/text#2Fxml"),
    })
    file_entry_obj = pdf_filestream._addObject(file_entry)
    # The Filespec entry
    ef_dict = DictionaryObject({
        NameObject("/F"): file_entry_obj,
        NameObject('/UF'): file_entry_obj,
    })

    fname_obj = createStringObject(XML_FILENAME)
    filespec_dict = DictionaryObject({
        NameObject("/AFRelationship"): NameObject("/Data"),
        NameObject("/Desc"): createStringObject("e-Invoice"),
        NameObject("/Type"): NameObject("/Filespec"),
        NameObject("/F"): fname_obj,
        NameObject("/EF"): ef_dict,
        NameObject("/UF"): fname_obj,
    })
    filespec_obj = pdf_filestream._addObject(filespec_dict)
    name_arrayobj_cdict = {fname_obj: filespec_obj}
    name_arrayobj_content_sort = list(
        sorted(name_arrayobj_cdict.items(), key=lambda x: x[0]))
    name_arrayobj_content_final = []
    af_list = []
    for (fname_obj, filespec_obj) in name_arrayobj_content_sort:
        name_arrayobj_content_final += [fname_obj, filespec_obj]
        af_list.append(filespec_obj)
    embedded_files_names_dict = DictionaryObject({
        NameObject("/Names"): ArrayObject(name_arrayobj_content_final),
    })
    # Then create the entry for the root, as it needs a
    # reference to the Filespec
    embedded_files_dict = DictionaryObject({
        NameObject("/EmbeddedFiles"): embedded_files_names_dict,
    })
    res_output_intents = []
    for output_intent_dict, dest_output_profile_dict in output_intents:
        dest_output_profile_obj = pdf_filestream._addObject(
            dest_output_profile_dict)
        # TODO detect if there are no other objects in output_intent_dest_obj
        # than /DestOutputProfile
        output_intent_dict.update({
            NameObject("/DestOutputProfile"): dest_output_profile_obj,
        })
        output_intent_obj = pdf_filestream._addObject(output_intent_dict)
        res_output_intents.append(output_intent_obj)
    # Update the root
    metadata_xml_str = _prepare_pdf_metadata_xml(pdf_metadata)
    metadata_file_entry = DecodedStreamObject()
    metadata_file_entry.setData(metadata_xml_str)
    metadata_file_entry.update({
        NameObject('/Subtype'): NameObject('/XML'),
        NameObject('/Type'): NameObject('/Metadata'),
    })
    metadata_obj = pdf_filestream._addObject(metadata_file_entry)
    af_value_obj = pdf_filestream._addObject(ArrayObject(af_list))
    pdf_filestream._root_object.update({
        NameObject("/AF"): af_value_obj,
        NameObject("/Metadata"): metadata_obj,
        NameObject("/Names"): embedded_files_dict,
        # show attachments when opening PDF
        NameObject("/PageMode"): NameObject("/UseAttachments"),
    })
    if res_output_intents:
        pdf_filestream._root_object.update({
            NameObject("/OutputIntents"): ArrayObject(res_output_intents),
        })
    metadata_txt_dict = _prepare_pdf_metadata_txt(pdf_metadata)
    pdf_filestream.addMetadata(metadata_txt_dict)


def _get_original_output_intents(original_pdf):
    output_intents = []
    try:
        pdf_root = original_pdf.trailer['/Root']
        ori_output_intents = pdf_root['/OutputIntents']
        for ori_output_intent in ori_output_intents:
            ori_output_intent_dict = ori_output_intent.getObject()
            dest_output_profile_dict = \
                ori_output_intent_dict['/DestOutputProfile'].getObject()
            output_intents.append(
                (ori_output_intent_dict, dest_output_profile_dict))
    except:
        pass
    return output_intents


def add_xml_binary_pdf(pdf_content, xml_content, check_xsd=False, pdf_metadata=None):
    """
    Embed XML content into PDF file

    :param pdf_content: PDF document as a binary string
    :param xml_content: XML content to integrate (either ETree object or string)
    :param check_xsd: check the XML content against XSD
    :param pdf_metadata: Specify the metadata of the generated PDF.
    If pdf_metadata is None (default value), this lib will generate some
    metadata in English by extracting relevant info from the XML.
    Here is an example for the pdf_metadata argument:
    pdf_metadata = {
        'author': 'Robolabs',
        'keywords': 'e-Invoice, Invoice',
        'title': 'Robolabs: Invoice I1242',
        'subject':
          'e-invoice invoice KL0001 dated 2020-06-01 issued by Robolabs',
        }
    If you pass the pdf_metadata argument, you will not use the automatic
    generation based on the extraction of the XML file, which will
    bring a very small perf improvement.
    :return: The PDF with embedded XML data, as a binary string
    """

    if not isinstance(pdf_content, bytes):
        raise ValueError('pdf_invoice argument must be a string')
    final_pdf = False
    with NamedTemporaryFile(prefix='doc-with-embedded-xml', suffix='.pdf') as f:
        f.write(pdf_content)
        add_xml_to_pdf_file(f, xml_content,
                            check_xsd=check_xsd, pdf_metadata=pdf_metadata)
        f.seek(0)
        final_pdf = f.read()
        f.close()
    return final_pdf


def add_xml_to_pdf_file(pdf_file, xml_content, check_xsd=True, pdf_metadata=None, output_pdf_file=None):
    """
    Generate a e-invoice from a regular PDF invoice and a XML file.
    The method uses a file as input (regular PDF invoice) and re-writes
    the file (PDF invoice).
    :param pdf_file: a pdf file
    :param xml_content: XML content as a str or etree
    :param check_xsd: check the XML content against XSDif enable, checks the XML file against the XSD
    :param pdf_metadata: Specify the metadata of the generated PDF.
    If pdf_metadata is None (default value), this lib will generate some
    metadata in English by extracting relevant info from the XML.
    Here is an example for the pdf_metadata argument:
    pdf_metadata = {
        'author': 'Robolabs',
        'keywords': 'e-Invoice, Invoice',
        'title': 'Robolabs: Invoice I1242',
        'subject':
          'e-invoice invoice KL0001 dated 2020-06-01 issued by Robolabs',
        }
    If you pass the pdf_metadata argument, you will not use the automatic
    generation based on the extraction of the  XML file, which will
    bring a very small perf improvement.
    :param output_pdf_file: File Path to the output  PDF file
    :type output_pdf_file: string or unicode
    :return: Returns True. This method re-writes the input PDF invoice file,
    unless if the output_pdf_file is provided.
    :rtype: bool
    """
    #TODO: add xsd validation
    if not pdf_file:
        raise ValueError('Missing pdf_invoice argument')
    if not xml_content:
        raise ValueError('Missing xml_content argument')
    if not isinstance(check_xsd, bool):
        raise ValueError('check_xsd argument must be a boolean')
    if not isinstance(pdf_metadata, (type(None), dict)):
        raise ValueError('pdf_metadata argument must be a dict or None')
    if not isinstance(pdf_metadata, (dict, type(None))):
        raise ValueError('pdf_metadata argument must be a dict or None')
    if isinstance(pdf_file, (str, unicode)):
        file_type = 'path'
    else:
        file_type = 'file'
    xml_root = None
    # in Python3, xml_string is a byte
    if isinstance(xml_content, (str, bytes)):
        xml_string = xml_content
    elif isinstance(xml_content, unicode):
        xml_string = xml_content.encode('utf8')
    elif isinstance(xml_content, type(etree.Element('HelloWorld'))):
        xml_root = xml_content
        xml_string = etree.tostring(
            xml_root, pretty_print=True, encoding='UTF-8',
            xml_declaration=True)
    elif isinstance(xml_content, file):
        xml_content.seek(0)
        xml_string = xml_content.read()
        xml_content.close()
    else:
        raise TypeError(
            "The second argument of the method add_xml_to_pdf_file must be "
            "either a string, an etree.Element() object or a file "
            "(it is a %s)." % type(xml_content))
    if pdf_metadata is None:
        pass
        # if xml_root is None:
        #     xml_root = etree.fromstring(xml_string)
        # base_info = _extract_base_info(xml_root)
        # pdf_metadata = _base_info2pdf_metadata(base_info)
    else:
        # clean-up pdf_metadata dict
        for key, value in pdf_metadata.items():
            if not isinstance(value, (str, unicode)):
                pdf_metadata[key] = ''
    if check_xsd:
        res, msg = validate_xsd(xml_string, flavor='esaskaita')
        if not res:
            raise exceptions.ValidationError(_('The generated XML did not pass validation:\n%s') % msg)
    original_pdf = PdfFileReader(pdf_file)
    # Extract /OutputIntents obj from original invoice
    output_intents = _get_original_output_intents(original_pdf)
    new_pdf_filestream = PdfFileWriter()
    new_pdf_filestream._header = b_("%PDF-1.4")
    new_pdf_filestream.appendPagesFromReader(original_pdf)

    original_pdf_id = original_pdf.trailer.get('/ID')
    if original_pdf_id:
        new_pdf_filestream._ID = original_pdf_id
    pdf_update_metadata_add_attachment(new_pdf_filestream, xml_string, pdf_metadata, output_intents=output_intents)
    if file_type == 'path':
        with open(pdf_file, 'wb') as f:
            new_pdf_filestream.write(f)
            f.close()
    elif file_type == 'file':
        new_pdf_filestream.write(pdf_file)
    return True


def _parse_embeddedfiles_kids_node(kids_node, level, res):
    if level not in [1, 2]:
        raise ValueError('Level argument should be 1 or 2')
    if not isinstance(kids_node, list):
        logger.error(
            'The /Kids entry of the EmbeddedFiles name tree must '
            'be an array')
        return False
    logger.debug("kids_node=%s", kids_node)
    for kid_entry in kids_node:
        if not isinstance(kid_entry, IndirectObject):
            logger.error(
                'The /Kids entry of the EmbeddedFiles name tree '
                'must be a list of IndirectObjects')
            return False
        kids_node = kid_entry.getObject()
        logger.debug('kids_node=%s', kids_node)
        if not isinstance(kids_node, dict):
            logger.error(
                'The /Kids entry of the EmbeddedFiles name tree '
                'must be a list of IndirectObjects that point to '
                'dict objects')
            return False
        if '/Names' in kids_node:
            if not isinstance(kids_node['/Names'], list):
                logger.error(
                    'The /Names entry in EmbeddedFiles must be an array')
                return False
            res += kids_node['/Names']
        elif '/Kids' in kids_node and level == 1:
            kids_node_l2 = kids_node['/Kids']
            _parse_embeddedfiles_kids_node(kids_node_l2, 2, res)
        else:
            logger.error('/Kids node should have a /Names or /Kids entry')
            return False
    return True


def _get_embeddedfiles(embeddedfiles_node):
    if not isinstance(embeddedfiles_node, dict):
        raise ValueError('The EmbeddedFiles node must be a dict')
    res = []
    if '/Names' in embeddedfiles_node:
        if not isinstance(embeddedfiles_node['/Names'], list):
            logger.error(
                'The /Names entry of the EmbeddedFiles name tree must '
                'be an array')
            return False
        res = embeddedfiles_node['/Names']
    elif '/Kids' in embeddedfiles_node:
        kids_node = embeddedfiles_node['/Kids']
        parse_result = _parse_embeddedfiles_kids_node(kids_node, 1, res)
        if parse_result is False:
            return False
    else:
        logger.error(
            'The EmbeddedFiles name tree should have either a /Names '
            'or a /Kids entry')
        return False
    if len(res) % 2 != 0:
        logger.error(
            'The EmbeddedFiles name tree should point to an even number of '
            'elements')
        return False
    return res


def get_embedded_xml_from_pdf(pdf_file, check_xsd=False):
    """
    Retrieve XML file embedded in the PDF
    :param pdf_file:
    :param check_xsd:
    :return:
    """
    if not pdf_file:
        raise ValueError('Missing pdf_file argument')
    if not isinstance(check_xsd, bool):
        raise ValueError('Missing check_xsd argument')
    if isinstance(pdf_file, str):
        pdf_file = BytesIO(pdf_file)
    elif isinstance(pdf_file, file):
        pdf_file = pdf_file
    else:
        raise TypeError(
            "The first argument of the method get_embedded_xml_from_pdf must "
            "be either a string or a file (it is a %s)." % type(pdf_file))
    xml_string = xml_filename = False
    pdf = PdfFileReader(pdf_file)
    pdf_root = pdf.trailer['/Root']  # = Catalog
    catalog_name = _get_dict_entry(pdf_root, '/Names')
    if not catalog_name:
        return None, None
    embeddedfiles_node = _get_dict_entry(catalog_name, '/EmbeddedFiles')
    if not embeddedfiles_node:
        return None, None
    embeddedfiles = _get_embeddedfiles(embeddedfiles_node)
    if not embeddedfiles:
        return None, None
    embeddedfiles_by_two = list(zip(embeddedfiles, embeddedfiles[1:]))[::2]
    try:
        for (filename, file_obj) in embeddedfiles_by_two:
            if filename in [XML_FILENAME]:
                xml_file_dict = file_obj.getObject()
                tmp_xml_string = xml_file_dict['/EF']['/F'].getData()
                if check_xsd:
                    res, msg = validate_xsd(tmp_xml_string, flavor='esaskaita')
                    if not res:
                        continue
                xml_string = tmp_xml_string
                xml_filename = filename
                break
    except:
        logger.error('No valid XML file found in the PDF')
        return None, None
    return xml_filename, xml_string


def _prepare_pdf_metadata_txt(pdf_metadata):
    pdf_date = _get_pdf_timestamp()
    info_dict = {
        '/Author': pdf_metadata.get('author', ''),
        '/CreationDate': pdf_date,
        '/Creator': 'Robolabs',
        '/Keywords': pdf_metadata.get('keywords', ''),
        '/ModDate': pdf_date,
        '/Subject': pdf_metadata.get('subject', ''),
        '/Title': pdf_metadata.get('title', ''),
    }
    return info_dict


def _prepare_pdf_metadata_xml(pdf_metadata):
    xml_str = """
<?xpacket begin="\ufeff" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description xmlns:pdfaid="http://www.aiim.org/pdfa/ns/id/" rdf:about="">
      <pdfaid:part>3</pdfaid:part>
      <pdfaid:conformance>B</pdfaid:conformance>
    </rdf:Description>
    <rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/" rdf:about="">
      <dc:title>
        <rdf:Alt>
          <rdf:li xml:lang="x-default">{title}</rdf:li>
        </rdf:Alt>
      </dc:title>
      <dc:creator>
        <rdf:Seq>
          <rdf:li>{author}</rdf:li>
        </rdf:Seq>
      </dc:creator>
      <dc:description>
        <rdf:Alt>
          <rdf:li xml:lang="x-default">{subject}</rdf:li>
        </rdf:Alt>
      </dc:description>
    </rdf:Description>
    <rdf:Description xmlns:pdf="http://ns.adobe.com/pdf/1.4/" rdf:about="">
      <pdf:Producer>{producer}</pdf:Producer>
    </rdf:Description>
    <rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/" rdf:about="">
      <xmp:CreatorTool>{creator_tool}</xmp:CreatorTool>
      <xmp:CreateDate>{timestamp}</xmp:CreateDate>
      <xmp:ModifyDate>{timestamp}</xmp:ModifyDate>
    </rdf:Description>
    <rdf:Description xmlns:pdfaExtension="http://www.aiim.org/pdfa/ns/extension/" xmlns:pdfaSchema="http://www.aiim.org/pdfa/ns/schema#" xmlns:pdfaProperty="http://www.aiim.org/pdfa/ns/property#" rdf:about="">
      <pdfaExtension:schemas>
        <rdf:Bag>
          <rdf:li rdf:parseType="Resource">
            <pdfaSchema:schema>eInvoice XML PDFA Extension Schema</pdfaSchema:schema>
            <pdfaSchema:namespaceURI>urn:e-saskaita:pdfa:CrossIndustryDocument:invoice:1p0#</pdfaSchema:namespaceURI>
            <pdfaSchema:prefix>fx</pdfaSchema:prefix>
            <pdfaSchema:property>
              <rdf:Seq>
                <rdf:li rdf:parseType="Resource">
                  <pdfaProperty:name>DocumentFileName</pdfaProperty:name>
                  <pdfaProperty:valueType>Text</pdfaProperty:valueType>
                  <pdfaProperty:category>external</pdfaProperty:category>
                  <pdfaProperty:description>name of the embedded XML invoice file</pdfaProperty:description>
                </rdf:li>
                <rdf:li rdf:parseType="Resource">
                  <pdfaProperty:name>DocumentType</pdfaProperty:name>
                  <pdfaProperty:valueType>Text</pdfaProperty:valueType>
                  <pdfaProperty:category>external</pdfaProperty:category>
                  <pdfaProperty:description>INVOICE</pdfaProperty:description>
                </rdf:li>
                <rdf:li rdf:parseType="Resource">
                  <pdfaProperty:name>Version</pdfaProperty:name>
                  <pdfaProperty:valueType>Text</pdfaProperty:valueType>
                  <pdfaProperty:category>external</pdfaProperty:category>
                  <pdfaProperty:description>The actual version of the XML schema</pdfaProperty:description>
                </rdf:li>
                <rdf:li rdf:parseType="Resource">
                  <pdfaProperty:name>ConformanceLevel</pdfaProperty:name>
                  <pdfaProperty:valueType>Text</pdfaProperty:valueType>
                  <pdfaProperty:category>external</pdfaProperty:category>
                  <pdfaProperty:description>The conformance level of the embedded Factur-X data</pdfaProperty:description>
                </rdf:li>
              </rdf:Seq>
            </pdfaSchema:property>
          </rdf:li>
        </rdf:Bag>
      </pdfaExtension:schemas>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>
"""
    xml_str = xml_str.format(
        title=pdf_metadata.get('title', ''),
        author=pdf_metadata.get('author', ''),
        subject=pdf_metadata.get('subject', ''),
        producer='PyPDF4',
        creator_tool='Robolabs',
        timestamp=_get_metadata_timestamp(),
    )
    xml_byte = xml_str.encode('utf-8')
    logger.debug('metadata XML:')
    logger.debug(xml_byte)
    return xml_byte
