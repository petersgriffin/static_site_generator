import argparse
import configparser
from datetime import datetime
import json
import logging
from logging.handlers import TimedRotatingFileHandler
import os
import re
import subprocess
from operator import itemgetter, attrgetter

from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = None
config = None


def load_site_data(start_dir):
    """ loads each page sourcefile, returns them in a central 'site' dict. """
    site = {}
    site['pages'] = {}
    site['tags'] = {}
    site['date_hierarchy'] = {}
    site['months'] = ['January', 'February', 'March', 'April', 'May', 'June',
                      'July', 'August', 'September', 'October', 'November',
                      'December']  # avoids importing another date library
    site['output_dir_name'] = start_dir.split('/')[-1]
    logger.info('Output dir name: {}'.format(site['output_dir_name']))

    def recursively_load_subdirs(current_dir):
        with os.scandir(current_dir) as dir_iterator:
            for path_item in dir_iterator:
                if path_item.name == 'skip_rendering':
                    return
        with os.scandir(current_dir) as dir_iterator:
            for path_item in dir_iterator:
                if path_item.name.endswith('.html') and path_item.is_file():
                    page = process_page_file(path_item.path, start_dir)
                    site['pages'][page['page_id']] = page

                elif path_item.is_dir():
                    recursively_load_subdirs(path_item.path)

    recursively_load_subdirs(start_dir)
    if 'index' not in site['pages'].keys():
        logger.error(f"index.html file not parsed in {start_dir}")
        raise FileNotFoundError
    site['name'] = site['pages']['index']['title']
    return site


def process_page_file(path, start_dir):
    """ loads a page from a sourcefile, and returns it as a dict. """
    logger.debug(f'Loading: {path} / {start_dir}')
    page = {}
    page['date'] = None
    page['order'] = 0
    page['tags'] = []
    page['children'] = []
    page['siblings'] = []
    page['ancestors'] = []

    page_id = path[len(start_dir):].lstrip('./').split('.')[0]
    page['page_id'] = page_id
    page['path'] = page_id.split('/')
    page['filename'] = page['path'][-1]
    page['depth'] = len(page_id.split('/')) - 1

    if page_id == 'index':
        page['parent'] = None
    elif page['depth'] == 0:
        page['parent'] = 'index'
    else:
        page['parent'] = page_id[:page_id.rfind('/')]

    logger.debug(f"Page ID   : {page['page_id']}")
    logger.debug(f"     path : {page['path']}")
    logger.debug(f" filename : {page['filename']}")
    logger.debug(f"    depth : {page['depth']}")
    logger.debug(f"   parent : {page['parent']}")

    file_string = None
    with open(path) as f:
        file_string = f.read()

    split_on = config['main']['split_sequence']
    if split_on not in file_string:
        logger.error(f'Split Sequence "{split_on}" missing from file {path}')
        raise ValueError

    splitted = file_string.split(split_on, maxsplit=1)
    metadata_section = splitted[0]
    html_section = splitted[1]

    for line in metadata_section.splitlines():
        split_field = line.split(':', maxsplit=1)
        field_name = split_field[0]
        field_value = split_field[1].strip()

        if field_name == 'tags':
            page['tags'] = [t.strip().replace(' ', '_').lower() for t in field_value.split(',') if len(t) > 0]
            if len(page['tags']) == 0:
                page['tags'].append('untagged')

        elif field_name == 'date':
            page['date'] = datetime.strptime(field_value, '%Y-%M-%d')
            page['year'] = page['date'].strftime('%Y')
            page['month'] = page['date'].strftime('%M')

        elif field_name == 'order':
            page['order'] = int(field_value)

        else:
            page[field_name] = field_value

    page['html'] = process_macros(html_section)
    return page


def interlink_pages_for_navigation(site):
    """ Adds page relationship metadata to the site-dict, and returns it. """
    for page_id, page in site['pages'].items():
        logger.debug(f"Interlinking {page_id}")
        if not page['parent']:
            continue
        parent_page = site['pages'][page['parent']]
        parent_page['children'].append(page['page_id'])

        for sub_page_id, sub_page in site['pages'].items():
            if page['parent'] == sub_page['parent']:
                page['siblings'].append(sub_page_id)

        for t in page['tags']:
            if t not in site['tags'].keys():
                site['tags'][t] = []
            site['tags'][t].append(page_id)

        if page['date']:
            month = page['month']
            year = page['year']
            if year not in site['date_hierarchy'].keys():
                site['date_hierarchy'][year] = {}
            if month not in site['date_hierarchy'][year].keys():
                site['date_hierarchy'][year][month] = []
            site['date_hierarchy'][year][month].append(page_id)

        def get_ancestors(pid, ancestors):
            p = site['pages'][pid]
            if pid == 'index':
                return ancestors
            if 'parent' in p.keys():
                ancestors.append(p['parent'])
            return get_ancestors(p['parent'], ancestors)

        page['ancestors'] = get_ancestors(page_id, [])
        page['ancestors'].reverse()

        logger.debug(f"ancestors: {page['ancestors']}")
        logger.debug(f"children:  {page['children']}")
        logger.debug(f"siblings:  {page['siblings']}")

        if not (page['ancestors'][0] == 'index' or page_id == 'index'):
            logger.error(f"{page_id}, or its ultimate ancestor is not 'index'")
            raise ValueError


def sort_pages_for_navigation(site):
    """
        Pages default to alphabetical sort on title in the nav lists. Author
        can add an 'order' integer to the source page, low positive values to
        force to the top of the list, with negative order counting from the end
        e.g. order: -2 is penultimate position and order: 4 is 4th listing.
        Duplicate order values in source files are OK.
    """
    for page_id, page in site['pages'].items():
        if page['order'] <= 0:
            page['order'] = len(page['siblings']) - page['order']

        def sort_page_ids(page_ids):
            """ Sorts list of page_ids based on attributes of the pages """
            li = [site['pages'][p] for p in page_ids]
            li.sort(key=itemgetter('order', 'title'))
            return [p['page_id'] for p in li]

        page['children'] = sort_page_ids(page['children'])
        page['siblings'] = sort_page_ids(page['siblings'])


def process_macros(content_string):
    """ Performs macro replacement on the provided string and returns it. """
    # escape characters
    esc = ['{{', '}}']

    def get_link_html(m):
        return f'<a href="{m.group(1)}">{m.group(2)}</a>'

    link = re.compile(f"""{esc[0]}\\s*link\\s*\\("(.*?)"\\s*,\\s*"(.*?)"\\s*\\)\\s*{esc[1]}""")
    content_string = re.sub(link, get_link_html, content_string)

    def get_image_html(m):
        return f'<img src="{m.group(1)}" alt="{m.group(2)}"/>'

    image = re.compile(f"""{esc[0]}\\s*image\\s*\\("(.*?)"\\s*,\\s*"(.*?)"\\s*\\)\\s*{esc[1]}""")
    content_string = re.sub(image, get_image_html, content_string)

    def get_scaled_image_html(m):
        return f"<img src=\"{m.group(1)}\" alt=\"{m.group(2)}\" height=\"{m.group(3)}\" width=\"{m.group(4)}\"/>"

    image = re.compile(f"""{esc[0]}\\s*imagehw\\s*\\("(.*?)"\\s*,\\s*"(.*?)"\\s*,\\s*"(.*?)"\\s*,\\s*"(.*?)"\\s*\\)\\s*{esc[1]}""")
    content_string = re.sub(image, get_scaled_image_html, content_string)

    return content_string


def render_html(site, output_path, dry_run):
    """ Finalizes the site and write it to the output directory. """
    loader = FileSystemLoader('templates', encoding='utf-8')
    jinja_env = Environment(loader=loader,
                            autoescape=select_autoescape(['xml']))

    def write_to_file(target_path, html_string):
        if dry_run:
            logger.warning(f'No-write test for {target_path}...')
            return

        with open(target_path, 'w') as f:
            logger.info(f'Writing html to {target_path}...')
            f.write(str(html_string))

    # 404 / error pages
    jtmp = jinja_env.get_template('error.html')
    html = jtmp.render(site=site, page={'title': 'Error of some kind',
                                        'depth': 0,
                                        'page_id': 'error'})
    write_to_file(f"{output_path}/error.html", html)

    # regular pages, from the source files
    for page_id, page in site['pages'].items():
        jtmp = jinja_env.get_template('post.html')
        html = jtmp.render(page=page, site=site)
        write_to_file(f"{output_path}/{page['page_id']}.html", html)

        html = jtmp.render(page=page, site=site, print_version=True)
        write_to_file(f"{output_path}/{page['page_id']}_print.html", html)

    # tag aggregation page
    if not dry_run:
        os.makedirs(f'{output_path}/tags', exist_ok=True)
    jtmp = jinja_env.get_template('tag_list.html')
    html = jtmp.render(site=site,
                       page={'title': 'tags',
                             'depth': 0,
                             'page_id': 'tags'})
    write_to_file(f'{output_path}/tags.html', html)

    # a page for each individual tag
    for t in site['tags']:
        jtmp = jinja_env.get_template('tag.html')
        html = jtmp.render(tag=t, site=site,
                           page={'title': t,
                                 'depth': 1,
                                 'page_id': f'tags/{{t}}'})
        write_to_file(f'{output_path}/tags/{t}.html', html)

    # year-month date indices, if any pages are dated
    if len(site['date_hierarchy'].items()) > 0:
        if not dry_run:
            os.makedirs(f'{output_path}/date', exist_ok=True)
        jtmp = jinja_env.get_template('month_list.html')
        html = jtmp.render(site=site,
                           page={'title': 'Date Index',
                                 'depth': 0,
                                 'page_id': 'date'})
        write_to_file(f'{output_path}/dates.html', html)

        for y in site['date_hierarchy'].keys():
            for m in site['date_hierarchy'][y]:
                page_ids = site['date_hierarchy'][y][m]
                if not dry_run:
                    os.makedirs(f'{output_path}/{y}', exist_ok=True)
                jtmp = jinja_env.get_template('month.html')
                html = jtmp.render(site=site, month=m, year=y,
                                   page_ids=page_ids,
                                   month_name=site['months'][int(m) - 1],
                                   page={'title': f'{m}, {y}',
                                         'depth': 1,
                                         'page_id': f'{y}/{m}'})
                write_to_file(f'{output_path}/{y}/{m}.html', html)


def get_logger(config, log_level):
    logger = logging.getLogger(config['log']['logger_name'])

    stream_handler = logging.StreamHandler()
    handler = TimedRotatingFileHandler(filename=config['log']['filename'],
                                       interval=int(config['log']['interval']),
                                       when=config['log']['when'],
                                       backupCount=int(config['log']['count']))

    formatter = logging.Formatter(config['log']['msg_format'],
                                  config['log']['date_format'])
    handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)

    logger.addHandler(stream_handler)
    logger.addHandler(handler)

    logger.setLevel(log_level)
    return logger


def main():
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.description = """
Processes a directory tree of custom-format text files into a static website.

Source directory recursively copied to output directory, including images and
other static files.

Source files (those ending in .html) contain a metadata header, a delimeter
sequence, and the rest of the file is for the custom page HTML, including
convenience macros.

Final site navigation / URL hierarchy maps to source directory structure and
internal 'page_id':
   - site_data/example.com/index.html           = index
   - site_data/example.com/news.html            = news
   -    output/example.com/news/2019/10_06.html = news/2019/10_06
   -   https://example.com/news/2019/10_06.html  <--- published URL

Requires one index.html at site root, with no others permitted."""

    parser.epilog = 'CAUTION: program does not delete files between runs.'

    parser.add_argument('source_site_root', metavar='source-site-root',
                        help='Root directory of the input-source files.')

    parser.add_argument('output_path', metavar='output-path',
                        help='Output directory for rendered sites.')

    parser.add_argument('-v', '--verbosity', action='store_true',
                        help='Increases verbosity, sets logging to DEBUG.')

    parser.add_argument('--config-location', '-c',
                        help='Custom config file location.',
                        default='config.ini')

    parser.add_argument('--append-html', '-a', action='store_true',
                        help='Appends .html extension to internal links.')

    parser.add_argument('--dry-run', action='store_true',
                        help='Reads and processess site, skips writing files.')

    args = parser.parse_args()

    global config
    config = configparser.ConfigParser(allow_no_value=True)
    config.read(args.config_location)

    global logger
    subprocess.run(['mkdir', '-p', 'log'])
    if args.verbosity:
        logger = get_logger(config, logging.DEBUG)
    else:
        logger = get_logger(config, logging.INFO)

    proj_name = args.source_site_root.rsplit('/')[1]
    site_output_path = f'{args.output_path}/{proj_name}'

    site = load_site_data(args.source_site_root)

    interlink_pages_for_navigation(site)

    sort_pages_for_navigation(site)

    site['append_html'] = bool(args.append_html)

    if not args.dry_run:
        subprocess.run(['mkdir', '-p', site_output_path])
        subprocess.run(['cp', '-R', 'static', f'{site_output_path}/'])
        subprocess.run(['cp', '-R', args.source_site_root,
                        f'{args.output_path}/'])

    render_html(site, site_output_path, args.dry_run)


if __name__ == '__main__':
    main()
