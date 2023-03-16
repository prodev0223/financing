# -*- encoding: utf-8 -*-
from odoo import tools
import subprocess32 as subprocess
from lxml import etree, objectify
import psutil


def get_swed_data(env):
    """
    Method that fetches all of the SwedBank config data
    Key folders that must exist:
    root_directory-
        -received
        -sending
        -certs
        -processed
        -sent
        -sendingInvoices
        -receivedInvoices
    :return: SwedBank config data in dict format
    """
    # config = env['ir.config_parameter'].sudo()
    return {
        'directory_path': tools.config['swed_directory_path'],
        'cert_path': tools.config['swed_cert_path'],
        'main_url': tools.config['swed_main_url'],
    }


def kill(proc_pid):
    process = psutil.Process(proc_pid)
    for proc in process.children(recursive=True):
        proc.kill()
    process.kill()


def handle_timeout(proc):
    """
    Wait for a process to finish, or kill it after timeout
    :return: None
    """
    seconds = subprocess_timeout()
    try:
        proc.wait(seconds)
    except subprocess.TimeoutExpired:
        kill(proc.pid)


def xml_validator(some_xml_string, xsd_file='/path/to/my_schema_file.xsd'):
    try:
        schema = etree.XMLSchema(file=xsd_file)
        parser = objectify.makeparser(schema=schema)
        objectify.fromstring(some_xml_string, parser)
        return True, str()
    except Exception as exc:
        return False, exc.args[0]


def subprocess_timeout():
    return 30

