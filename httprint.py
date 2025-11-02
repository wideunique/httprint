#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""httprint - print files via web

Copyright 2019 Davide Alberani <da@mimante.net>

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import os
import re
import time
import glob
import shutil
import logging
import subprocess
import multiprocessing as mp
import threading
import uuid
from types import SimpleNamespace

import yaml

from tornado.ioloop import IOLoop
import tornado.httpserver
import tornado.web
from tornado import gen, escape

import configparser

try:
    from PIL import Image
    import img2pdf
    IMAGE_SUPPORT = True
except ImportError:
    IMAGE_SUPPORT = False

# Check for LibreOffice availability
OFFICE_SUPPORT = False
LIBREOFFICE_CMD = None

def check_libreoffice():
    """Check if LibreOffice is available."""
    global OFFICE_SUPPORT, LIBREOFFICE_CMD

    # Try common LibreOffice command names
    for cmd in ['libreoffice', 'soffice', '/Applications/LibreOffice.app/Contents/MacOS/soffice']:
        try:
            result = subprocess.run([cmd, '--version'],
                                   capture_output=True,
                                   timeout=5,
                                   text=True)
            if result.returncode == 0:
                OFFICE_SUPPORT = True
                LIBREOFFICE_CMD = cmd
                logger.info(f"LibreOffice found: {cmd}")
                logger.info(f"Version: {result.stdout.strip()}")
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue

    logger.warning("LibreOffice not found. Office document support disabled.")
    return False

API_VERSION = '1.0'
QUEUE_DIR = 'queue'
ARCHIVE = True
ARCHIVE_DIR = 'archive'
PRINT_CMD = 'lp -n %(copies)s -o sides=%(sides)s -o media=%(media)s'

MAX_PAGES = 10

logger = logging.getLogger()
logger.setLevel(logging.INFO)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE_ENV = 'HTTPRINT_CONFIG'
CONFIG_DEFAULT_FILENAME = 'config.yaml'

DEFAULT_CONFIG = {
    'port': 7777,
    'address': '',
    'ssl_cert': os.path.join(BASE_DIR, 'ssl', 'httprint_cert.pem'),
    'ssl_key': os.path.join(BASE_DIR, 'ssl', 'httprint_key.pem'),
    'max_pages': MAX_PAGES,
    'queue_dir': QUEUE_DIR,
    'archive': ARCHIVE,
    'archive_dir': ARCHIVE_DIR,
    'pdf_only': True,
    'check_pdf_pages': True,
    'print_cmd': PRINT_CMD,
    'debug': False,
    'demo': False,
}


def load_config(path=None):
    """Load configuration from YAML, applying defaults."""
    if path is None:
        path = os.environ.get(CONFIG_FILE_ENV) or os.path.join(BASE_DIR, CONFIG_DEFAULT_FILENAME)

    data = {}
    if path and os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as fh:
            loaded = yaml.safe_load(fh) or {}
        if not isinstance(loaded, dict):
            raise RuntimeError("Configuration file must contain a mapping at the top level")
        data = loaded
    elif path and os.path.exists(path):
        raise RuntimeError(f"Configuration path exists but is not a file: {path}")

    config = DEFAULT_CONFIG.copy()
    for key, value in data.items():
        normalized_key = key.replace('-', '_')
        config[normalized_key] = value

    return SimpleNamespace(**config)

def normalize_page_ranges(page_spec, total_pages):
    """Validate and normalize a page specification string."""
    if page_spec is None or str(page_spec).strip() == '':
        return None
    if total_pages <= 0:
        raise ValueError('unknown document page count')
    parts = []
    for raw_part in str(page_spec).split(','):
        part = raw_part.strip()
        if not part:
            raise ValueError('invalid page specification format')
        if '-' in part:
            start_text, end_text = part.split('-', 1)
            start_text = start_text.strip()
            end_text = end_text.strip()
            if not start_text.isdigit() or not end_text.isdigit():
                raise ValueError('page ranges must be numeric')
            start = int(start_text)
            end = int(end_text)
            if start < 1 or end < 1:
                raise ValueError('page numbers must be >= 1')
            if start > end:
                raise ValueError('range start cannot exceed end')
            if end > total_pages:
                raise ValueError('page range exceeds document length')
            parts.append(f"{start}-{end}")
        else:
            if not part.isdigit():
                raise ValueError('page numbers must be numeric')
            page = int(part)
            if page < 1:
                raise ValueError('page numbers must be >= 1')
            if page > total_pages:
                raise ValueError('page number out of bounds')
            parts.append(str(page))
    return ','.join(parts)

re_pages = re.compile(r'^Pages:\s+(\d+)$', re.M | re.I)


class HTTPrintBaseException(Exception):
    """Base class for httprint custom exceptions.

    :param message: text message
    :type message: str
    :param status: numeric http status code
    :type status: int"""
    def __init__(self, message, status=400):
        super(HTTPrintBaseException, self).__init__(message)
        self.message = message
        self.status = status


class BaseHandler(tornado.web.RequestHandler):
    """Base class for request handlers."""
    # A property to access the first value of each argument.
    arguments = property(lambda self: dict([(k, v[0].decode('utf-8'))
                                            for k, v in self.request.arguments.items()]))

    @property
    def clean_body(self):
        """Return a clean dictionary from a JSON body, suitable for a query on MongoDB.

        :returns: a clean copy of the body arguments
        :rtype: dict"""
        return escape.json_decode(self.request.body or '{}')

    def write_error(self, status_code, **kwargs):
        """Default error handler."""
        if isinstance(kwargs.get('exc_info', (None, None))[1], HTTPrintBaseException):
            exc = kwargs['exc_info'][1]
            status_code = exc.status
            message = exc.message
        else:
            message = 'internal error'
        self.build_error(message, status=status_code)

    def initialize(self, **kwargs):
        """Add every passed (key, value) as attributes of the instance."""
        for key, value in kwargs.items():
            setattr(self, key, value)

    def build_error(self, message='', status=400):
        """Build and write an error message.

        :param message: textual message
        :type message: str
        :param status: HTTP status code
        :type status: int
        """
        self.set_status(status)
        self.write({'error': True, 'message': message})

    def build_success(self, message='', status=200):
        """Build and write a success message.

        :param message: textual message
        :type message: str
        :param status: HTTP status code
        :type status: int
        """
        self.set_status(status)
        self.write({'error': False, 'message': message})

    def _run(self, cmd, fname, callback=None):
        p = subprocess.Popen(cmd, close_fds=True)
        p.communicate()
        if callback:
            callback(cmd, fname, p)

    def _archive(self, cmd, fname, p):
        if os.path.isfile('%s.keep' % fname):
            return
        if self.cfg.archive:
            if not os.path.isdir(self.cfg.archive_dir):
                os.makedirs(self.cfg.archive_dir)
            for fn in glob.glob(fname + '*'):
                shutil.move(fn, self.cfg.archive_dir)
        for fn in glob.glob(fname + '*'):
            try:
                os.unlink(fn)
            except Exception:
                pass

    def run_subprocess(self, cmd, fname, callback=None):
        """Execute the given action asynchronously.

        Use a thread to avoid multiprocessing pickling issues with bound methods
        under spawn start-method environments (e.g., macOS/Python 3.8+).
        """
        t = threading.Thread(target=self._run, args=(cmd, fname, callback), daemon=True)
        t.start()

    def print_file(self, fname, page_ranges=None):
        copies = 1
        sides = "two-sided-long-edge"
        media = "A4"

        config = configparser.ConfigParser()
        config.read(fname + '.info')
        printconf = config['print']
        copies = printconf.getint('copies')
        if copies < 1:
            copies = 1
        sides = printconf.get('sides')
        media = printconf.get('media')

        print_cmd = self.cfg.print_cmd.split(' ')
        cmd = [x % {'copies': copies, 'sides': sides, 'media': media} for x in print_cmd]
        if page_ranges:
            cmd.extend(['-o', f'page-ranges={page_ranges}'])
        cmd.append(fname)
        print (cmd)

        # Demo mode: simulate printing without calling real printer
        if self.cfg.demo:
            import time
            simulated_job_id = f"demo-print-{int(time.time())}"
            logger.info("[DEMO MODE] Would execute print command:")
            logger.info("Command: %s", ' '.join(cmd))
            logger.info("File: %s", fname)
            logger.info("Copies: %d", copies)
            logger.info("Sides: %s", sides)
            logger.info("Media: %s", media)
            if page_ranges:
                logger.info("Page ranges: %s", page_ranges)
            logger.info("Simulated job ID: %s", simulated_job_id)
            # Still perform archiving if enabled
            # Create a mock process object for _archive callback
            class MockProcess:
                returncode = 0
            self._archive(cmd, fname, MockProcess())
        else:
            self.run_subprocess(cmd, fname, self._archive)

class UploadHandler(BaseHandler):
    """File upload handler."""
    def is_image_file(self, filename):
        """Check if file is an image based on extension."""
        if not IMAGE_SUPPORT:
            return False
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif'}
        ext = os.path.splitext(filename.lower())[1]
        return ext in image_extensions

    def convert_images_to_pdf(self, image_files, output_pdf):
        """Convert multiple images to a single PDF file with A4 page fitting."""
        if not IMAGE_SUPPORT:
            raise Exception("Image support not available. Please install Pillow and img2pdf.")

        try:
            # A4 size in points (1 inch = 72 points)
            # A4 portrait: 210mm × 297mm = 595.28 × 841.89 points
            a4_portrait = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))

            # Use layout_fun to ensure images fit within A4 page
            # This method correctly scales images to fit the page while maintaining aspect ratio
            layout_fun = img2pdf.get_layout_fun(a4_portrait)

            with open(output_pdf, 'wb') as f:
                f.write(img2pdf.convert(
                    image_files,
                    layout_fun=layout_fun,
                    rotation=img2pdf.Rotation.ifvalid
                ))

            logger.info("Converted %d image(s) to PDF with A4 page fitting", len(image_files))
            return True
        except Exception as e:
            logger.error("Error converting images to PDF: %s", e)
            return False

    def is_office_file(self, filename):
        """Check if file is an Office document based on extension."""
        if not OFFICE_SUPPORT:
            return False
        office_extensions = {'.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}
        ext = os.path.splitext(filename.lower())[1]
        return ext in office_extensions

    def convert_office_to_pdf(self, office_file, output_pdf, timeout=60):
        """Convert Office document to PDF using LibreOffice."""
        if not OFFICE_SUPPORT:
            raise Exception("Office document support not available. Please install LibreOffice.")

        try:
            # Get the directory where the output PDF should be created
            output_dir = os.path.dirname(output_pdf)

            # LibreOffice command to convert to PDF
            cmd = [
                LIBREOFFICE_CMD,
                '--headless',
                '--convert-to', 'pdf',
                '--outdir', output_dir,
                office_file
            ]

            logger.info(f"Converting Office document to PDF: {' '.join(cmd)}")

            # Run conversion with timeout
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=timeout,
                text=True
            )

            if result.returncode != 0:
                logger.error(f"LibreOffice conversion failed: {result.stderr}")
                return False, f"conversion failed: {result.stderr}"

            # LibreOffice creates a file with the same name but .pdf extension
            # in the output directory
            base_name = os.path.splitext(os.path.basename(office_file))[0]
            expected_pdf = os.path.join(output_dir, f"{base_name}.pdf")

            # If the expected PDF exists and is different from output_pdf, rename it
            if os.path.exists(expected_pdf) and expected_pdf != output_pdf:
                shutil.move(expected_pdf, output_pdf)

            if not os.path.exists(output_pdf):
                logger.error(f"Converted PDF not found: {output_pdf}")
                return False, "converted PDF not found"

            logger.info(f"Successfully converted to PDF: {output_pdf}")
            return True, None

        except subprocess.TimeoutExpired:
            logger.error(f"LibreOffice conversion timeout after {timeout} seconds")
            return False, f"conversion timeout after {timeout} seconds"
        except Exception as e:
            logger.error(f"Error converting Office document to PDF: {e}")
            return False, str(e)

    @gen.coroutine
    def post(self):
        if not self.request.files.get('file'):
            self.build_error("no file uploaded")
            return
        copies = 1

        #questi per ora stanno qui perche' non sso come implemtare la parte web
        media = "A4"
        color = False

        try:
            copies = int(self.get_argument('copies'))
            if copies < 1:
                copies = 1
        except Exception:
            pass
        if copies > self.cfg.max_pages:
            self.build_error('you have asked too many copies')
            return

        page_spec = self.get_argument('pages', default=None)
        if page_spec is not None:
            page_spec = page_spec.strip() or None

        double_param = self.get_argument('double_sided', default='true')
        double_str = str(double_param).strip().lower() if double_param is not None else 'true'
        if double_str in ('true', '1', 'yes', 'on'):
            double_sided = True
        elif double_str in ('false', '0', 'no', 'off'):
            double_sided = False
        else:
            self.build_error('invalid value for double_sided')
            return

        sides = "two-sided-long-edge" if double_sided else "one-sided"

        # Get all uploaded files
        uploaded_files = self.request.files['file']

        # Check if all files are images, PDFs, or Office documents
        all_images = all(self.is_image_file(f['filename']) for f in uploaded_files)
        all_pdfs = all(f['filename'].lower().endswith('.pdf') for f in uploaded_files)
        all_office = all(self.is_office_file(f['filename']) for f in uploaded_files)

        # Count file types
        has_images = any(self.is_image_file(f['filename']) for f in uploaded_files)
        has_pdfs = any(f['filename'].lower().endswith('.pdf') for f in uploaded_files)
        has_office = any(self.is_office_file(f['filename']) for f in uploaded_files)

        # Check for mixed types or unsupported files
        if not all_images and not all_pdfs and not all_office:
            # Check for mixed types
            type_count = sum([has_images, has_pdfs, has_office])
            if type_count > 1:
                self.build_error("cannot mix different file types in one upload")
                return

            # Check for unsupported file types
            for f in uploaded_files:
                if not self.is_image_file(f['filename']) and \
                   not f['filename'].lower().endswith('.pdf') and \
                   not self.is_office_file(f['filename']):
                    self.build_error(f"unsupported file type: {f['filename']}")
                    return

        if not os.path.isdir(self.cfg.queue_dir):
            os.makedirs(self.cfg.queue_dir)
        now = time.strftime('%Y%m%d%H%M%S')
        unique_id = str(uuid.uuid4())[:8]  # Use first 8 chars of UUID for shorter filenames

        # Handle multiple images - convert to PDF
        if all_images and len(uploaded_files) > 1:
            # Save images temporarily
            temp_image_files = []
            try:
                for idx, fileinfo in enumerate(uploaded_files):
                    temp_fname = os.path.join(self.cfg.queue_dir, f'temp_{unique_id}_{idx}_{fileinfo["filename"]}')
                    with open(temp_fname, 'wb') as fd:
                        fd.write(fileinfo['body'])
                    temp_image_files.append(temp_fname)

                # Convert images to PDF
                fname = f'{now}_{unique_id}.pdf'
                pname = os.path.join(self.cfg.queue_dir, fname)
                if not self.convert_images_to_pdf(temp_image_files, pname):
                    self.build_error("failed to convert images to PDF")
                    return

                webFname = f"{len(uploaded_files)} images combined"
                extension = '.pdf'
            finally:
                # Clean up temporary image files
                for temp_file in temp_image_files:
                    try:
                        os.unlink(temp_file)
                    except Exception:
                        pass

        # Handle single image - convert to PDF
        elif all_images and len(uploaded_files) == 1:
            fileinfo = uploaded_files[0]
            temp_fname = os.path.join(self.cfg.queue_dir, f'temp_{unique_id}_{fileinfo["filename"]}')
            try:
                with open(temp_fname, 'wb') as fd:
                    fd.write(fileinfo['body'])

                fname = f'{now}_{unique_id}.pdf'
                pname = os.path.join(self.cfg.queue_dir, fname)
                if not self.convert_images_to_pdf([temp_fname], pname):
                    self.build_error("failed to convert image to PDF")
                    return

                webFname = fileinfo['filename']
                extension = '.pdf'
            finally:
                try:
                    os.unlink(temp_fname)
                except Exception:
                    pass

        # Handle Office document - convert to PDF
        elif all_office and len(uploaded_files) == 1:
            fileinfo = uploaded_files[0]
            webFname = fileinfo['filename']
            original_ext = os.path.splitext(webFname)[1].lower()

            # Save Office file temporarily
            temp_office_fname = os.path.join(self.cfg.queue_dir, f'temp_{unique_id}_{fileinfo["filename"]}')
            try:
                with open(temp_office_fname, 'wb') as fd:
                    fd.write(fileinfo['body'])

                # Convert to PDF
                fname = f'{now}_{unique_id}.pdf'
                pname = os.path.join(self.cfg.queue_dir, fname)

                success, error_msg = self.convert_office_to_pdf(temp_office_fname, pname)
                if not success:
                    self.build_error(f"failed to convert Office document to PDF: {error_msg}")
                    return

                extension = '.pdf'
            finally:
                # Clean up temporary Office file
                try:
                    os.unlink(temp_office_fname)
                except Exception:
                    pass

        # Handle single PDF (original behavior)
        elif len(uploaded_files) == 1:
            fileinfo = uploaded_files[0]
            webFname = fileinfo['filename']
            extension = ''
            try:
                extension = os.path.splitext(webFname)[1]
            except Exception:
                pass
            fname = f'{now}_{unique_id}{extension}'
            pname = os.path.join(self.cfg.queue_dir, fname)
            try:
                with open(pname, 'wb') as fd:
                    fd.write(fileinfo['body'])
            except Exception as e:
                self.build_error("error writing file %s: %s" % (pname, e))
                return

        # Handle multiple PDFs - not supported yet
        else:
            self.build_error("multiple PDF files not supported, please upload one PDF or multiple images")
            return

        #questo l'ho aggiuto io. ho qualche dubbio su dove settare la variabile config
        config = configparser.ConfigParser()
        config['print'] = {}
        printconf = config['print']
        printconf['name'] = '%s' % webFname
        printconf['date'] = '%s' % now
        printconf['copies'] = '%d' % copies
        printconf['sides'] = '%s' % sides
        printconf['media'] = '%s' % media
        printconf['color'] = '%s' % color
        printconf['double_sided'] = 'true' if double_sided else 'false'

        failure = False
        if self.cfg.check_pdf_pages or self.cfg.pdf_only:
            try:
                p = subprocess.Popen(['pdfinfo', pname], stdout=subprocess.PIPE)
                out, _ = p.communicate()
                if p.returncode != 0 and self.cfg.pdf_only:
                    self.build_error('the uploaded file does not seem to be a PDF')
                    failure = True
                out = out.decode('utf-8', errors='ignore')
                pages = int(re_pages.findall(out)[0])
                if pages * copies > self.cfg.max_pages and self.cfg.check_pdf_pages and not failure:
                    self.build_error('too many pages to print (%d)' % (pages * copies))
                    failure = True
            except Exception:
                if not failure:
                    self.build_error('unable to get PDF information')
                    failure = True
                pass
        if failure:
            for fn in glob.glob(pname + '*'):
                try:
                    os.unlink(fn)
                except Exception:
                    pass
            return

        # Get total pages from PDF before printing (in case file gets archived)
        total_pages = 0
        try:
            p = subprocess.Popen(['pdfinfo', pname], stdout=subprocess.PIPE)
            out, _ = p.communicate()
            if p.returncode == 0:
                out = out.decode('utf-8', errors='ignore')
                pages_match = re_pages.findall(out)
                if pages_match:
                    total_pages = int(pages_match[0])
        except Exception:
            pass

        normalized_pages = None
        if page_spec is not None:
            try:
                normalized_pages = normalize_page_ranges(page_spec, total_pages)
            except ValueError as exc:
                self.build_error(str(exc))
                for fn in glob.glob(pname + '*'):
                    try:
                        os.unlink(fn)
                    except Exception:
                        pass
                return

        if total_pages > 0:
            printconf['total_pages'] = '%d' % total_pages
        if normalized_pages:
            printconf['page_ranges'] = normalized_pages
        else:
            printconf.pop('page_ranges', None)
        try:
            with open(pname + '.info', 'w') as configfile:
                config.write(configfile)
        except Exception:
            pass

        # Upload and print directly
        self.print_file(pname, page_ranges=normalized_pages)

        # Build success response with details
        total_images = len(uploaded_files) if all_images else 0
        original_format = None

        # Determine original format for Office documents
        if all_office:
            original_format = os.path.splitext(webFname)[1].lower().lstrip('.')

        response = {"error": False, "message": "file sent to printer"}
        if total_images > 0 or total_pages > 0 or original_format or normalized_pages or double_sided is not None:
            response["details"] = {}
            if total_images > 0:
                response["details"]["total_images"] = total_images
            if original_format:
                response["details"]["original_format"] = original_format
            if total_pages > 0:
                response["details"]["total_pages"] = total_pages
            if normalized_pages:
                response["details"]["page_ranges"] = normalized_pages
            response["details"]["double_sided"] = double_sided

        self.write(response)


class TemplateHandler(BaseHandler):
    """Handler for the template files in the / path."""
    @gen.coroutine
    def get(self, *args, **kwargs):
        """Get a template file."""
        page = 'index.html'
        if args and args[0]:
            page = args[0].strip('/')
        arguments = self.arguments
        self.render(page, **arguments)


def serve(config_path=None):
    """Read YAML configuration and start the server."""
    cfg = load_config(config_path)

    if cfg.debug:
        logger.setLevel(logging.DEBUG)

    # Check for LibreOffice availability
    check_libreoffice()

    ssl_options = {}
    if cfg.ssl_key and cfg.ssl_cert and \
            os.path.isfile(cfg.ssl_key) and os.path.isfile(cfg.ssl_cert):
        ssl_options = dict(certfile=cfg.ssl_cert, keyfile=cfg.ssl_key)

    init_params = dict(listen_port=cfg.port, logger=logger, ssl_options=ssl_options, cfg=cfg)

    _upload_path = r'upload/?'
    application = tornado.web.Application([
            (r'/api/%s' % _upload_path, UploadHandler, init_params),
            (r'/api/v%s/%s' % (API_VERSION, _upload_path), UploadHandler, init_params),
            (r'/?(.*)', TemplateHandler, init_params),
        ],
        static_path=os.path.join(os.path.dirname(__file__), 'dist/static'),
        template_path=os.path.join(os.path.dirname(__file__), 'dist/'),
        debug=cfg.debug)
    http_server = tornado.httpserver.HTTPServer(application, ssl_options=ssl_options or None)
    logger.info('Start serving on %s://%s:%d', 'https' if ssl_options else 'http',
                                                 cfg.address if cfg.address else '127.0.0.1',
                                                 cfg.port)
    http_server.listen(cfg.port, cfg.address)
    try:
        IOLoop.instance().start()
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == '__main__':
    serve()
