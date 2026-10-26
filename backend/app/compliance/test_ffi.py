#!/usr/bin/env python3
# ==========================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
#
# ==========================================================

"""Minimal FFI test."""

import ctypes
from pathlib import Path

# Load DLL
dll_path = Path(__file__).parent / "amc_compliance_rs.dll"
print(f"Loading DLL from: {dll_path}")
dll = ctypes.CDLL(str(dll_path))

# Test basic function
print("Attempting to call validate_input_query_c...")

try:
    # Set up types
    validate_func = dll.validate_input_query_c
    validate_func.argtypes = [ctypes.c_char_p]
    validate_func.restype = ctypes.c_void_p
    
    # Call with test query
    query = b"What is exit load?"
    print(f"Calling with query: {query}")
    result_ptr = validate_func(query)
    print(f"Got result pointer: {result_ptr}")
    
    if result_ptr:
        print("Success!")
    else:
        print("Returned NULL")

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
