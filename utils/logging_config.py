"""
Centralized logging configuration for Hytale Server Manager.
"""

import logging
import os
from logging.handlers import RotatingFileHandler


def setup_logging(app=None, log_dir='logs'):
    """
    Configure application-wide logging.

    Args:
        app: Flask application instance (optional). If provided, configures
             Flask's app.logger as well.
        log_dir: Directory for log files. Created if it does not exist.
    """
    os.makedirs(log_dir, exist_ok=True)

    log_format = '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    formatter = logging.Formatter(log_format)

    # Rotating file handler: 5 MB per file, keep 5 backups
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, 'gotale.log'),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8',
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    # Console handler
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.setLevel(logging.DEBUG)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)

    # Quiet noisy libraries
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    logging.getLogger('engineio').setLevel(logging.WARNING)
    logging.getLogger('socketio').setLevel(logging.WARNING)

    # Configure Flask's app.logger if an app is provided
    if app is not None:
        app.logger.setLevel(logging.DEBUG)
        # Avoid duplicate handlers if Flask already added some
        for handler in [file_handler, stream_handler]:
            if handler not in app.logger.handlers:
                app.logger.addHandler(handler)
