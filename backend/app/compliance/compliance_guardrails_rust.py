# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
#
# Author: NuSummit Developers
# ===========================================================================

"""
Rust-based Compliance Guardrails via ctypes FFI.
High-performance input/output validation using Rust compiled binaries.
Falls back to pure Python if Rust module not available.
"""

import ctypes
import logging
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("compliance.guardrails_rust")

# Determine DLL path
_dll_dir = Path(__file__).parent
_dll_path_win = _dll_dir / "amc_compliance_rs.dll"
_dll_path_unix = _dll_dir / "libamc_compliance_rs.so"

_rust_lib = None
_has_rust = False

def _load_rust_lib():
    """Attempt to load Rust-compiled library."""
    global _rust_lib, _has_rust
    
    if _has_rust:
        return True
    
    if sys.platform == "win32" and _dll_path_win.exists():
        try:
            _rust_lib = ctypes.CDLL(str(_dll_path_win))
            _has_rust = True
            logger.info("Loaded Rust compliance guardrails from %s", _dll_path_win)
            
            # Set up function signatures
            _rust_lib.validate_input_query_c.argtypes = [ctypes.c_char_p]
            _rust_lib.validate_input_query_c.restype = ctypes.c_void_p
            
            _rust_lib.validate_llm_output_c.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
            _rust_lib.validate_llm_output_c.restype = ctypes.c_void_p
            
            _rust_lib.free_input_result.argtypes = [ctypes.c_void_p]
            _rust_lib.free_input_result.restype = None
            
            _rust_lib.free_output_result.argtypes = [ctypes.c_void_p]
            _rust_lib.free_output_result.restype = None
            
            return True
        except Exception as e:
            logger.warning("Failed to load Rust DLL from %s: %s", _dll_path_win, e)
    elif sys.platform != "win32" and _dll_path_unix.exists():
        try:
            _rust_lib = ctypes.CDLL(str(_dll_path_unix))
            _has_rust = True
            logger.info("Loaded Rust compliance guardrails from %s", _dll_path_unix)
            
            # Set up function signatures
            _rust_lib.validate_input_query_c.argtypes = [ctypes.c_char_p]
            _rust_lib.validate_input_query_c.restype = ctypes.c_void_p
            
            _rust_lib.validate_llm_output_c.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p]
            _rust_lib.validate_llm_output_c.restype = ctypes.c_void_p
            
            return True
        except Exception as e:
            logger.warning("Failed to load Rust library from %s: %s", _dll_path_unix, e)
    
    _has_rust = False
    return False


# C struct definitions (must match Rust structs)
class InputValidationResult(ctypes.Structure):
    """Result from input validation."""
    _fields_ = [
        ("is_safe", ctypes.c_bool),
        ("risk_flag_ptr", ctypes.c_void_p),  # Pointer to C string
        ("sanitized_query_ptr", ctypes.c_void_p),  # Pointer to C string
    ]


class OutputValidationResult(ctypes.Structure):
    """Result from output validation."""
    _fields_ = [
        ("is_valid", ctypes.c_bool),
        ("modified_answer_ptr", ctypes.c_void_p),  # Pointer to C string
        ("advice_shield_triggered", ctypes.c_bool),
        ("reasons_count", ctypes.c_size_t),
        ("reasons_ptr", ctypes.c_void_p),  # Pointer to array of C strings
    ]


def _decode_c_string(ptr: ctypes.c_void_p) -> Optional[str]:
    """Safely decode a C string pointer."""
    if not ptr:
        return None
    try:
        # Cast void pointer to char* and decode
        c_str = ctypes.cast(ptr, ctypes.c_char_p)
        return c_str.value.decode("utf-8") if c_str.value else None
    except Exception as e:
        logger.warning(f"Failed to decode C string: {e}")
        return None


def validate_input_query(query: str) -> Dict[str, Any]:
    """
    Validate incoming user query against prompt injection and safety rules.
    Uses Rust implementation if available, falls back to minimal Python.
    """
    if not _load_rust_lib():
        logger.debug("Rust library not available, using Python fallback")
        return _validate_input_query_py(query)
    
    if not query:
        return {"is_safe": True, "risk_flag": None, "sanitized_query": query, "guardrail_engine": "Rust"}
    
    try:
        # Call Rust function
        query_bytes = query.encode("utf-8")
        result_ptr = _rust_lib.validate_input_query_c(query_bytes)
        
        if not result_ptr:
            return _validate_input_query_py(query)
        
        # Cast to struct
        result = ctypes.cast(result_ptr, ctypes.POINTER(InputValidationResult)).contents
        
        # Extract fields carefully
        is_safe = bool(result.is_safe)
        risk_flag = _decode_c_string(result.risk_flag_ptr)
        sanitized_query = _decode_c_string(result.sanitized_query_ptr) or query
        
        # Free Rust memory
        try:
            _rust_lib.free_input_result(result_ptr)
        except Exception as e:
            logger.warning(f"Failed to free input result: {e}")
        
        return {
            "is_safe": is_safe,
            "risk_flag": risk_flag,
            "sanitized_query": sanitized_query,
            "guardrail_engine": "Rust_InjectionShield",
        }
    
    except Exception as e:
        logger.exception(f"Error in Rust validate_input_query: {e}")
        return _validate_input_query_py(query)


def validate_llm_output(
    answer: str,
    context: str = "",
    domain_intent: str = "general"
) -> Dict[str, Any]:
    """
    Validate LLM output answer against compliance rules using Rust.
    Falls back to Python if Rust not available.
    """
    if not _load_rust_lib():
        logger.debug("Rust library not available, using Python fallback")
        return _validate_llm_output_py(answer, context, domain_intent)
    
    if not answer:
        return {
            "is_valid": True,
            "modified_answer": answer,
            "reasons": [],
            "advice_shield_triggered": False,
        }
    
    try:
        # Call Rust function
        answer_bytes = answer.encode("utf-8")
        context_bytes = context.encode("utf-8") if context else b""
        domain_bytes = domain_intent.encode("utf-8") if domain_intent else b"general"
        
        result_ptr = _rust_lib.validate_llm_output_c(answer_bytes, context_bytes, domain_bytes)
        
        if not result_ptr:
            return _validate_llm_output_py(answer, context, domain_intent)
        
        # Cast to struct
        result = ctypes.cast(result_ptr, ctypes.POINTER(OutputValidationResult)).contents
        
        # Extract fields carefully
        is_valid = bool(result.is_valid)
        modified_answer = _decode_c_string(result.modified_answer_ptr) or answer
        advice_triggered = bool(result.advice_shield_triggered)
        
        # Extract reasons array
        reasons = []
        if result.reasons_count > 0 and result.reasons_ptr:
            try:
                reasons_array = ctypes.cast(result.reasons_ptr, ctypes.POINTER(ctypes.c_char_p))
                for i in range(result.reasons_count):
                    reason = _decode_c_string(reasons_array[i])
                    if reason:
                        reasons.append(reason)
            except Exception as e:
                logger.warning(f"Failed to extract reasons: {e}")
        
        # Free Rust memory
        try:
            _rust_lib.free_output_result(result_ptr)
        except Exception as e:
            logger.warning(f"Failed to free output result: {e}")
        
        return {
            "is_valid": is_valid,
            "modified_answer": modified_answer,
            "reasons": reasons,
            "advice_shield_triggered": advice_triggered,
            "guardrail_engine": "Rust_OutputCompliance",
        }
    
    except Exception as e:
        logger.exception(f"Error in Rust validate_llm_output: {e}")
        return _validate_llm_output_py(answer, context, domain_intent)


# Python fallback implementations
def _validate_input_query_py(query: str) -> Dict[str, Any]:
    """Minimal Python fallback for input validation."""
    if not query:
        return {"is_safe": True, "risk_flag": None, "sanitized_query": query}
    
    # Simple check for obvious injection attempts
    if any(phrase in query.lower() for phrase in ["ignore previous", "system prompt", "bypass", "dan", "forget all"]):
        return {
            "is_safe": False,
            "risk_flag": "PROMPT_INJECTION_DETECTED",
            "sanitized_query": "[BLOCKED]",
            "guardrail_engine": "Python_Fallback",
        }
    
    return {
        "is_safe": True,
        "risk_flag": None,
        "sanitized_query": query,
        "guardrail_engine": "Python_Fallback",
    }


def _validate_llm_output_py(answer: str, context: str = "", domain_intent: str = "general") -> Dict[str, Any]:
    """Minimal Python fallback for output validation."""
    if not answer:
        return {
            "is_valid": True,
            "modified_answer": answer,
            "reasons": [],
            "advice_shield_triggered": False,
        }
    
    reasons = []
    modified = answer
    advice_triggered = False
    
    # Check for buy/sell advice
    if "recommend" in answer.lower() and ("buy" in answer.lower() or "sell" in answer.lower()):
        advice_triggered = True
        reasons.append("UNAUTHORIZED_FINANCIAL_ADVICE")
    
    # Add disclaimer if missing
    if "disclaimer" not in modified.lower() and "market risk" not in modified.lower():
        modified += "\n\n*Disclaimer: Subject to market risks.*"
        reasons.append("SEBI_DISCLAIMER_ENFORCED")
    
    return {
        "is_valid": True,
        "modified_answer": modified,
        "reasons": reasons,
        "advice_shield_triggered": advice_triggered,
        "guardrail_engine": "Python_Fallback",
    }
