# SPDX-License-Identifier: MIT
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] eartag {%(pathname)s:%(lineno)d} %(levelname)s: %(message)s",
)
