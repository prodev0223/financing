# Run this file as a regular python file to refactor modules by classes
# Run pycharm's code refactoring/import optimisation after.
# Double check each file after refactoring, _inherit field might be duplicated because this script simply puts stuff in
# the right place and does not perform 'smart field refactoring'. It also doesn't move global fields/vars to correct
# files after - so you have to do it yourself.
# Also you have to manually fix __init__.py
# I know this code is messy, I just needed it to work.

from os import listdir
from os.path import isfile, join
import re
from six import iteritems

ROBO_MODULES = ['l10n_lt']
BASE_PATH = '/home/bertrand/Documents/robo/robo/' # TODO CHANGE ROBO10 TO YOUR USER NAME
INIT_FILENAME = '__init__.py'
models = {}

def get_file_lines(file_path):
    f = open(file_path, "r")
    full_text = f.read()
    f.close()
    return full_text.splitlines()

def find_imported_files(dir_path):
    python_files = [f for f in listdir(dir_path) if isfile(join(dir_path, f)) and f[len(f) - 3:] == '.py']
    imported_files = []
    if INIT_FILENAME not in python_files:
        return imported_files
    init_location = dir_path + INIT_FILENAME
    init_lines = get_file_lines(init_location)
    number_of_lines = len(init_lines)
    index = 0
    imported_files = []
    while index < number_of_lines:
        line = init_lines[index]
        if 'import' in line:
            line_imported_files = line.split('import')[1].replace(' ', '')
            line_imported_files = line_imported_files.split(',')
            imported_files += line_imported_files
        index += 1
    return [f for f in python_files if f.replace('.py', '') in imported_files]

def get_file_imports(file_lines):
    number_of_lines = len(file_lines)
    index = 0
    inside_class = False
    end_of_class = False
    imports = []
    while index < number_of_lines:
        line = file_lines[index]
        if re.search('(^from\s+\S+\s+import\s+\S+|^import\s+\S+)', line):
            while index < number_of_lines:
                imports.append(line)
                if not re.search('\\$', line):
                    break
                index += 1
                line = file_lines[index]
        index += 1

    while index < number_of_lines:
        line = file_lines[index]
        if line and len(line) > 1 and line[:1] not in ['#', '', ' ']:
            inside_class = False
        if re.search('^class .*?\(models\..*?\):', line):
            inside_class = True
        if line[len(line) - 2:] == '()' and ' ' not in line:
            inside_class = end_of_class = True
        if not inside_class:
            imports.append(line)
        if end_of_class:
            inside_class = False
        end_of_class = False
        index += 1
    imports = [import_line for import_line in imports if import_line and import_line != '']
    imports = [import_line for import_line in imports if 'coding: utf-8' not in import_line]
    return imports

def get_file_classes(file_lines):
    number_of_lines = len(file_lines)
    index = 0
    classes = []
    while index < number_of_lines:
        line = file_lines[index]
        class_string = ''
        if re.search('^class .*?\(models\..*?\):', line):
            class_string += line + '\n'
            index += 1
            in_multiline_string = False
            while index < number_of_lines:
                line = file_lines[index]
                if in_multiline_string or len(line) == 0 or line[:1] in ['#', '', ' '] or line[:3] in ['\'\'\'', '\"\"\"']:
                    class_string += line + '\n'
                elif line[len(line) - 2:] == '()' and ' ' not in line:
                    class_string += line + '\n'
                    break
                else:
                    break
                index += 1
                if line_starts_or_stops_multiline_string(line):
                    in_multiline_string = not in_multiline_string
        if class_string and class_string != '':
            classes.append(class_string)
        index += 1
    return classes

def get_model_name(class_string):
    lines = class_string.splitlines()
    number_of_lines = len(lines)
    index = 0
    model_name = False
    while index < number_of_lines:
        line = lines[index]
        if re.search(' _name(\s=|=)', line):
            model_name_matches = re.search('[\'\"].*[\'\"]', line).regs
            model_name_matches = model_name_matches[len(model_name_matches) - 1]
            model_name = line[model_name_matches[0]:model_name_matches[1]].replace('\'', '').replace('\"', '')
            break
        index += 1
    if not model_name:
        index = 0
        while index < number_of_lines:
            line = lines[index]
            if re.search(' _inherit(\s=|=)', line):
                model_name_matches = re.search('[\'\"].*[\'\"]', line).regs
                model_name_matches = model_name_matches[len(model_name_matches) - 1]
                model_name = line[model_name_matches[0]:model_name_matches[1]].replace('\'', '').replace('\"', '')
                break
            index += 1
    if not model_name:
        raise Exception('MODULE NAME COULD NOT BE DETERMINED')
    return model_name

def get_proper_class_name(model_name):
    words = model_name.split('.')
    words = [word.capitalize() for word in words]
    return ''.join(words)

def determine_model_type(class_string):
    lines = class_string.splitlines()
    line = lines[0]
    reg_search = re.search('\(models\..*?\):', line)
    model_type = line[reg_search.regs[0][0]:reg_search.regs[0][1]]
    model_type = model_type.replace('.', '').replace('(', '').replace('):', '').replace('models', '')
    return model_type

def get_class_name_attribute(class_string):
    lines = class_string.splitlines()
    number_of_lines = len(lines)
    index = 0
    model_name = False
    while index < number_of_lines:
        line = lines[index]
        if re.search('( _name)', line):
            model_name_matches = re.search('[\'\"].*[\'\"]', line).regs
            model_name_matches = model_name_matches[len(model_name_matches) - 1]
            model_name = line[model_name_matches[0]:model_name_matches[1]].replace('\'', '').replace('\"', '')
        index += 1
    return model_name

def get_class_inherits(class_string):
    lines = class_string.splitlines()
    number_of_lines = len(lines)
    index = 0
    inherits = []
    while index < number_of_lines:
        line = lines[index]
        if re.search('( _inherit| _inherits)', line):
            inherit_matches = re.search('[\'\"].*[\'\"]', line).regs
            inherit_matches = inherit_matches[len(inherit_matches) - 1]
            inherit_matches = line[inherit_matches[0]:inherit_matches[1]].replace('\'', '').replace('\"', '')
            inherit_matches = inherit_matches.split(',')
            inherits += inherit_matches
        index += 1
    return inherits

def get_class_attributes(class_string):
    lines = class_string.splitlines()
    number_of_lines = len(lines)
    index = 0
    class_attributes = []
    while index < number_of_lines:
        line = lines[index]
        if re.search('\s*_\S*\s*=\s*', line):
            class_attributes.append(line)
        index += 1
    return class_attributes

def find_parens(s):
    toret = {}
    pstack = []

    for i, c in enumerate(s):
        if c == '(':
            pstack.append(i)
        elif c == ')':
            if len(pstack) == 0:
                raise IndexError("No matching closing parens at: " + str(i))
            toret[pstack.pop()] = i

    if len(pstack) > 0:
        raise IndexError("No matching opening parens at: " + str(pstack.pop()))

    return toret

def get_class_fields(class_string):
    lines = class_string.splitlines()
    number_of_lines = len(lines)
    index = 0
    fields = []
    while index < number_of_lines:
        total_field_string = lines[index]
        if re.search('\s{1,4}\S*\s*=\s*fields\..*?\(', total_field_string):
            try:
                find_parens(total_field_string)
            except:
                index += 1
                while index < number_of_lines:
                    line = lines[index]
                    total_field_string += '\n' + line
                    try:
                        find_parens(total_field_string)
                        break
                    except:
                        index += 1
            fields.append(total_field_string)
        index += 1
    return fields

def line_starts_or_stops_multiline_string(l):
    multiline_selectors = ['\'\'\'', '\"\"\"']
    for multiline_selector in multiline_selectors:
        selector_count = l.count(multiline_selector)
        if selector_count and (selector_count % 2 != 0):
            return True
    return False

def get_class_methods(class_string):
    lines = class_string.splitlines()
    number_of_lines = len(lines)
    index = 0
    methods = []
    method_start_reg_str = '\s*(def .*?:|@[a-zA-Z_])'

    while index < number_of_lines:
        line = lines[index]
        method_string = ''
        # COMMENTS AS METHODS
        while re.search('^\s*#', line):
            method_string += line + '\n'
            index += 1
            line = lines[index]
        if method_string != '':
            methods.append(method_string)
            continue
        if re.search(method_start_reg_str, line):
            spaces_before = ''
            while re.search(method_start_reg_str, line) and index < number_of_lines:
                method_string += line + '\n'
                if ' def ' in line:
                    spaces_before = line.split('def')[0]
                index += 1
                line = lines[index]
            inside_method = True
            in_multiline_string = False
            while inside_method and index < number_of_lines:
                line = lines[index]
                if not in_multiline_string and line and line != '' and line != '\n' and \
                        (line[:len(spaces_before)] != spaces_before or re.search('^\S', line[len(spaces_before):])) and \
                        not re.search('\s*#', line):
                    inside_method = False
                else:
                    method_string += line + '\n'
                    index += 1

                if line_starts_or_stops_multiline_string(line):
                    in_multiline_string = not in_multiline_string
            methods.append(method_string)
        else:
            index += 1
    return methods


for ROBO_MODULE in ROBO_MODULES:
    FULL_MODULE_PATH = BASE_PATH + ROBO_MODULE
    class_dirs = [f for f in listdir(FULL_MODULE_PATH) if f[:5] == 'model' or f[:6] == 'wizard']
    paths = ['{}/{}/'.format(FULL_MODULE_PATH, class_dir) for class_dir in class_dirs]

    model_data = {}

    for path in paths:
        python_files = find_imported_files(path)
        for py_file in python_files:
            if py_file != 'account_move_line.py':
                continue
            file_location = path + py_file

            file_lines = get_file_lines(file_location)
            imports = get_file_imports(file_lines)
            import_string = '\n'.join(imports)
            file_classes = get_file_classes(file_lines)

            f = open(file_location, "r")
            full_text = f.read()
            f.close()

            for import_x in imports:
                full_text = full_text.replace(import_x, '')

            for file_class in file_classes:
                model_name = get_model_name(file_class)
                class_name = get_proper_class_name(model_name)
                current_model_data = model_data.get(class_name, {})
                model_type = determine_model_type(file_class)
                if current_model_data.get('model_type') and current_model_data.get('model_type') != model_type:
                    raise Exception('Model type mismatch for model name {}'.format(model_name))
                current_model_data.update({
                    'model_type': model_type,
                    'model_name': model_name,
                    'class_name': class_name,
                })
                if not current_model_data.get('name_attribute'):
                    current_model_data.update({'name_attribute': get_class_name_attribute(file_class)})
                full_text = full_text.replace('\r', '')
                full_text = full_text.replace(file_class, '')
                methods = get_class_methods(file_class)
                for method in methods:
                    file_class = file_class.replace(method, '')
                fields = get_class_fields(file_class)
                for field in fields:
                    file_class = file_class.replace(field, '')

                class_attributes = get_class_attributes(file_class)
                for other_class_attribute in class_attributes:
                    file_class = file_class.replace(other_class_attribute, '')

                current_model_data.update({
                    'fields': current_model_data.get('fields', []) + fields,
                    'methods': current_model_data.get('methods', []) + methods,
                    'import_string': current_model_data.get('import_string', '') + '\n\n' + import_string,
                    'class_attributes': current_model_data.get('class_attributes', []) + class_attributes,
                })
                model_data.update({class_name: current_model_data})

                if not re.search('class\s*\S*\(models.\S*\):(\s*|\s*\S*\(\))$', file_class):
                    full_text += '\n\n\n' + file_class

            f = open(file_location, "w")
            f.write(full_text)
            f.close()

    MODEL_TYPE_DIR_MAPPING = {
        'TransientModel': [path for path in paths if '/wizard' in path][0]
    }
    for class_name, class_data in iteritems(model_data):
        file_name = class_data.get('model_name').replace('.', '_')+'.py'
        file_dir = MODEL_TYPE_DIR_MAPPING.get(class_data.get('model_type'), [path for path in paths if '/model' in path][0])
        file_loc = file_dir + file_name
        if isfile(file_loc):
            f = open(file_loc, "r")
            full_file = f.read() + class_data.get('import_string', '') + '\n'
            f.close()
        else:
            full_file = '# -*- coding: utf-8 -*-\n' + class_data.get('import_string', '') + '\n'
        full_file += '\n\n'
        full_file += 'class {}(models.{}):\n'.format(class_name, class_data.get('model_type'))
        name_attr = class_data.get('name_attribute')
        methods = class_data.get('methods', [])
        fields = class_data.get('fields', [])
        default_method_names = []
        for field in fields:
            everything_between_brackets = field[field.find("(")+1:field.rfind(")")]
            field_attrs = everything_between_brackets.split(',')
            for field_attr in field_attrs:
                default_attr = re.search('(\n\s*|\s*)(default\s*=|domain\s*=)', field_attr)
                if default_attr:
                    default_attr = field_attr[field_attr.find('=')+1:].replace(',', '').replace(' ', '')
                    if isinstance(default_attr, str):
                        default_method_names.append(default_attr)
        default_methods = []
        other_methods = []
        for method in methods:
            method_lines = method.splitlines()
            has_been_added = False
            for method_line in method_lines:
                is_definition_line = re.search(' def .*?:', method_line)
                if is_definition_line:
                    method_name = method_line.split(' def ')[1]
                    method_name = method_name.split('(')[0]
                    method_name = method_name.replace(' ', '')
                    if method_name in default_method_names:
                        default_methods.append(method)
                    else:
                        other_methods.append(method)
                    has_been_added = True
                    break
            if not has_been_added:
                other_methods.append(method)


        full_file += '\n'.join(list(set(class_data.get('class_attributes', [])))) + '\n\n'
        full_file += ''.join(default_methods) + '\n\n'
        full_file += '\n'.join(fields) + '\n\n'
        full_file += ''.join(other_methods) + '\n\n'

        f = open(file_loc, "w")
        f.write(full_file)
        f.close()