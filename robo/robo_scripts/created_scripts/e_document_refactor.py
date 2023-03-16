import os

from lxml import etree

# Sample python script to reformat e_document files.
# This script only removes fields, buttons and alerts that are found in a parent file using xpath.

document_base_path = "../../e_document/templates/requests/"
main_order_document = document_base_path + 'e_document_request.xml'

main_e_document_template_order_document = open(main_order_document)
main_document_xml = main_e_document_template_order_document.read()
main_document_root = etree.fromstring(main_document_xml)

documents = []
for x in os.listdir(document_base_path):
    if '.' not in x:
        documents.append(x)

for document in documents:
    document_folder_path = document_base_path + document + '/'
    document_files = os.listdir(document_folder_path)
    document_xmls = [document_file for document_file in document_files if '.xml' in document_file]
    if not document_xmls:
        print("Skipping document {} refactoring due to missing XML file.".format(document))
        continue
    elif len(document_xmls) > 1:
        print("Skipping document {} refactoring due to multiple XML files.".format(document))
        continue

    document_xml_file = open(document_folder_path + document_xmls[0], "r")
    xml = document_xml_file.read()
    root = etree.fromstring(xml)

    # Get rid of alerts
    alerts = root.xpath("//record[@model='ir.ui.view']/field[@name='arch']//div[contains(concat(' ',normalize-space(@class),' '),' alert ')]")
    main_document_alerts = main_document_root.xpath("//record[@model='ir.ui.view']/field[@name='arch']//div[contains(concat(' ',normalize-space(@class),' '),' alert ')]")
    if len(alerts) < 3:
        for alert in alerts:
            if alert.text in [a.text for a in main_document_alerts]:
                alert.getparent().remove(alert)

    document_view_fields = root.xpath("//record[@model='ir.ui.view']//field[@name='arch']//field")
    document_view_buttons = root.xpath("//record[@model='ir.ui.view']//field[@name='arch']//button")
    document_view_replacable_elements = document_view_fields + document_view_buttons

    for element in document_view_replacable_elements:
        element_name_attr = element.get('name')
        if element_name_attr:
            xpath_selector = "//field[@name='arch']//form//{0}[@name='{1}']".format(element.tag, element_name_attr)
            main_document_elements_alike = main_document_root.xpath(xpath_selector)
            if main_document_elements_alike:
                element.getparent().remove(element)

    document_xml_file.close()
    document_xml_file = open(document_folder_path + document_xmls[0], "w")
    document_xml_file.write(etree.tostring(root, pretty_print=True, encoding='utf-8'))
    document_xml_file.close()
