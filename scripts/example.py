#!/usr/bin/env python3

import logging

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


def main():
    print("Script executed successfully")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"Script failed: {e}")
        raise


