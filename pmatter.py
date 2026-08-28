#!/usr/bin/env python3
"""
Entry point for the Matter Polyglot v3 (PG3) node server.

This connects to a python-matter-server instance (host/port supplied by
the user via the PG3 Configuration parameters) and exposes discovered
Matter devices as ISY nodes.
"""
import sys

import udi_interface

from nodes.controller import Controller

LOGGER = udi_interface.LOGGER


if __name__ == "__main__":
    try:
        polyglot = udi_interface.Interface([])
        polyglot.start()

        Controller(polyglot, "controller", "controller", "PMatter Controller")

        polyglot.runForever()
    except (KeyboardInterrupt, SystemExit):
        LOGGER.warning("Received interrupt or exit, exiting...")
        sys.exit(0)
    except Exception as err:
        LOGGER.error("Startup failure: %s", err, exc_info=True)
        sys.exit(1)
