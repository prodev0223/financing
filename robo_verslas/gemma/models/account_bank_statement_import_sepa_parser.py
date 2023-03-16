# -*- coding: utf-8 -*-

from odoo import models, api
import re


class CamtParser(models.AbstractModel):
    _inherit = 'account.bank.statement.import.sepa.parser'

    @api.model
    def parse_external_partner_code(self, node_value):
        """
        Parse external polis/gemma partner code from node.
        Condition -- it must match one of the patterns
        :param node_value: sepa XML node value
        :return: partner code (str)
        """

        # Cant make better patterns, since length and everything else
        # might differ from code to code
        ext_code_patterns = ['30000', '10']
        found_code = str()

        # Node value must be of string type
        if not isinstance(node_value, basestring):
            return found_code

        for pattern in ext_code_patterns:
            # Skip if pattern is not in node value or if code is found
            if found_code or pattern not in node_value:
                continue

            # Split the node value on space
            node_values_split = node_value.split(' ')
            if len(node_values_split) == 1:
                potential_ext_code = node_values_split[0]

            else:
                # Take the longest value that matches the pattern
                ext_code_blocks = filter(lambda c: pattern in c, node_values_split)
                potential_ext_code = max(ext_code_blocks, key=lambda x: len(x))

            # Replace everything that is not digit
            potential_ext_code = re.sub('[^0-9]', str(), potential_ext_code)

            if len(potential_ext_code) > 6:
                found_code = potential_ext_code
        return found_code

    def add_code_from_node(self, ns, node, xpath_str, obj, attr_name):
        if not isinstance(xpath_str, (list, tuple)):
            xpath_str = [xpath_str]
        for search_str in xpath_str:
            found_node = node.xpath(search_str, namespaces={'ns': ns})
            if found_node:
                partner_code = self.parse_external_partner_code(found_node[0].text)
                if partner_code:
                    obj[attr_name] = partner_code
                    break

    def add_partner_name_code(self, ns, node, transaction):
        incoming = 1
        sign_node = node.xpath('ns:CdtDbtInd', namespaces={'ns': ns})
        if not sign_node:
            sign_node = node.xpath('./ns:NtryDtls/ns:TxDtls/ns:CdtDbtInd', namespaces={'ns': ns})
        if sign_node and sign_node[0].text == 'DBIT':
            incoming = -1
        if incoming == 1:
            partner_code_val_nodes = [
                './ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Dbtr/ns:Id/ns:PrvtId/ns:Othr/ns:Id',
                './ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Dbtr/ns:Id/ns:OrgId/ns:Othr/ns:Id',
            ]
            partner_code_type_node = [
                './ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Dbtr/ns:Id/ns:OrgId/ns:Othr/ns:SchmeNm/ns:Cd']

            partner_name_nodes = ['./ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Dbtr/ns:Nm']
            partner_ext_code_nodes = partner_code_val_nodes + \
                                     ['./ns:NtryDtls/ns:TxDtls/ns:RmtInf/ns:Strd/ns:CdtrRefInf/ns:Ref',
                                      './ns:NtryDtls/ns:TxDtls/ns:RmtInf/ns:Ustrd']
        else:
            partner_code_val_nodes = [
                './ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Cdtr/ns:Id/ns:PrvtId/ns:Othr/ns:Id',
                './ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Cdtr/ns:Id/ns:OrgId/ns:Othr/ns:Id',
            ]

            partner_code_type_node = [
                './ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Cdtr/ns:Id/ns:OrgId/ns:Othr/ns:SchmeNm/ns:Cd']

            partner_name_nodes = ['./ns:NtryDtls/ns:TxDtls/ns:RltdPties/ns:Cdtr/ns:Nm']
            partner_ext_code_nodes = partner_code_val_nodes + \
                                     ['./ns:NtryDtls/ns:TxDtls/ns:RmtInf/ns:Strd/ns:CdtrRefInf/ns:Ref',
                                      './ns:NtryDtls/ns:TxDtls/ns:RmtInf/ns:Ustrd']

        if not transaction.get('partner_inf'):
            code_type = self.check_value_from_node(
                ns, node, partner_code_type_node,
            )
            searchable = None
            if code_type == 'COID':
                searchable = 'kodas'
            elif code_type == 'TXID':
                searchable = 'vat'
            elif code_type == 'CUST':
                searchable = 'id'

            code_value = self.check_value_from_node(
                ns, node, partner_code_val_nodes,
            )
            transaction['partner_inf'] = (searchable, code_value)

        if not transaction.get('partner_name'):
            self.add_value_from_node(
                ns, node, partner_name_nodes,
                transaction, 'partner_name'
            )
        if not transaction.get('partner_code'):
            self.add_code_from_node(
                ns, node, partner_ext_code_nodes,
                transaction, 'partner_code'
            )


CamtParser()
