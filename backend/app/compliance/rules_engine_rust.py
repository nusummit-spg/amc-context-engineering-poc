# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
rules_engine_rust.py
====================
Python ctypes wrapper for Rust-based compliance rules engine.

Exposes Rust FFI functions with:
- Type-safe argument passing
- Memory management (string allocation/deallocation)
- Error handling and graceful fallback to Python
- Logging and performance metrics
"""

import ctypes
import json
import logging
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
import sys

logger = logging.getLogger("compliance.rules_engine_rust")


@dataclass
class RustLoadResult:
    """Result of Rust module loading attempt"""
    success: bool
    message: str
    library: Optional[ctypes.CDLL] = None
    dll_path: Optional[str] = None


class RulesEngineRustWrapper:
    """
    Python wrapper around Rust compliance rules engine.
    
    Features:
    - Lazy loading of Rust DLL (graceful fallback if not found)
    - Pre-compiled rules caching (one-time parse cost)
    - Memory management (free allocated strings)
    - Error handling and logging
    - Fallback to Python implementation if Rust unavailable
    """
    
    # Platform-specific library names
    LIBRARY_NAMES = {
        "windows": "compliance_rules_rs.dll",
        "linux": "libcompliance_rules_rs.so",
        "darwin": "libcompliance_rules_rs.dylib",
    }
    
    def __init__(self, fallback_engine=None):
        """
        Initialize Rust wrapper.
        
        Args:
            fallback_engine: Optional Python RulesEngine for fallback
        """
        self.lib: Optional[ctypes.CDLL] = None
        self.is_available = False
        self.compiled_rules_json: Optional[str] = None
        self.original_rules_json: Optional[str] = None  # Keep original for FFI calls
        self.fallback_engine = fallback_engine
        self.dll_path: Optional[str] = None
        
        # Try to load Rust library
        self._load_library()
    
    def _detect_platform(self) -> str:
        """Detect platform"""
        if sys.platform.startswith("win"):
            return "windows"
        elif sys.platform.startswith("linux"):
            return "linux"
        elif sys.platform.startswith("darwin"):
            return "darwin"
        else:
            return "linux"  # Default fallback
    
    def _find_library(self) -> Optional[Path]:
        """Find Rust library in common locations"""
        platform = self._detect_platform()
        lib_name = self.LIBRARY_NAMES.get(platform, "compliance_rules_rs.dll")
        
        # Check environment variable first
        env_path = os.environ.get("RUST_RULES_ENGINE_PATH")
        if env_path:
            lib_path = Path(env_path) / lib_name
            if lib_path.exists():
                return lib_path
        
        # Hard-coded absolute path (common location)
        hardcoded_path = Path(r"c:\Users\Laptopadmin\Desktop\context-engineering\rust\compliance_rules_rs\target\release") / lib_name
        if hardcoded_path.exists():
            return hardcoded_path
        
        # Search paths (in order)
        search_paths = [
            # Local directory
            Path(".") / lib_name,
            # Sibling directory
            Path(__file__).parent / lib_name,
            # Rust build output (from backend dir)
            Path(__file__).parent.parent.parent / "rust" / "compliance_rules_rs" / "target" / "release" / lib_name,
            # Also try from cwd
            Path.cwd() / "rust" / "compliance_rules_rs" / "target" / "release" / lib_name,
            # System paths (handled by ctypes.CDLL)
        ]
        
        for path in search_paths:
            logger.debug(f"Checking path: {path}")
            if path.exists():
                logger.info(f"Found Rust library at: {path}")
                return path
        
        logger.debug(f"Rust library not found in any search paths")
        return None
    
    def _load_library(self) -> RustLoadResult:
        """
        Attempt to load Rust library.
        
        Returns:
            RustLoadResult with success status and details
        """
        try:
            lib_path = self._find_library()
            
            if not lib_path:
                # Try system path
                platform = self._detect_platform()
                lib_name = self.LIBRARY_NAMES[platform]
                logger.debug(f"Attempting to load {lib_name} from system path...")
                
                try:
                    self.lib = ctypes.CDLL(lib_name)
                    self.is_available = True
                    logger.info(f"Loaded Rust library from system path: {lib_name}")
                    return RustLoadResult(
                        success=True,
                        message=f"Loaded {lib_name} from system path",
                        library=self.lib,
                        dll_path=lib_name
                    )
                except OSError as e:
                    return RustLoadResult(
                        success=False,
                        message=f"Rust library not found. Set RUST_RULES_ENGINE_PATH to DLL location. Error: {e}",
                        library=None
                    )
            
            # Load from found path
            self.lib = ctypes.CDLL(str(lib_path))
            self.dll_path = str(lib_path)
            self.is_available = True
            
            # Set up FFI function signatures
            self._setup_ffi_signatures()
            
            logger.info(f"Successfully loaded Rust rules engine from: {lib_path}")
            return RustLoadResult(
                success=True,
                message=f"Loaded Rust library from: {lib_path}",
                library=self.lib,
                dll_path=str(lib_path)
            )
        
        except Exception as e:
            logger.warning(f"Failed to load Rust library: {e}. Will use Python fallback.")
            self.is_available = False
            return RustLoadResult(
                success=False,
                message=f"Failed to load Rust library: {e}",
                library=None
            )
    
    def _setup_ffi_signatures(self):
        """Set up ctypes function signatures"""
        if not self.lib:
            return
        
        # compile_rules(rules_json: *const c_char) -> *mut c_char
        self.lib.compile_rules.argtypes = [ctypes.c_char_p]
        self.lib.compile_rules.restype = ctypes.POINTER(ctypes.c_char)
        
        # evaluate_funds_batch_ffi(funds_json: *const c_char, rules_json: *const c_char) -> *mut c_char
        self.lib.evaluate_funds_batch_ffi.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self.lib.evaluate_funds_batch_ffi.restype = ctypes.POINTER(ctypes.c_char)
        
        # evaluate_fund_ffi(fund_json: *const c_char, rules_json: *const c_char) -> *mut c_char
        self.lib.evaluate_fund_ffi.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self.lib.evaluate_fund_ffi.restype = ctypes.POINTER(ctypes.c_char)
        
        # free_rust_string(ptr: *mut c_char)
        self.lib.free_rust_string.argtypes = [ctypes.POINTER(ctypes.c_char)]
        self.lib.free_rust_string.restype = None
    
    def _c_string_to_python(self, c_str: ctypes.POINTER(ctypes.c_char)) -> str:
        """Convert C string to Python string and free memory"""
        if not c_str:
            return ""
        
        try:
            py_str = ctypes.string_at(c_str).decode('utf-8')
            return py_str
        finally:
            if self.lib and c_str:
                self.lib.free_rust_string(c_str)
    
    def compile_rules(self, rules: List[Dict[str, Any]]) -> bool:
        """
        Pre-compile rules at startup (one-time cost).
        
        Args:
            rules: List of rule dictionaries
        
        Returns:
            True if successful, False if using fallback
        """
        if not self.is_available:
            logger.debug("Rust engine not available, skipping pre-compilation")
            return False
        
        try:
            rules_json = json.dumps(rules)
            rules_bytes = rules_json.encode('utf-8')
            
            # IMPORTANT: Keep original rules JSON for FFI calls
            # The evaluate_funds_batch_ffi expects original rules with "condition" fields
            self.original_rules_json = rules_json
            
            logger.debug(f"Pre-compiling {len(rules)} rules in Rust...")
            
            result_ptr = self.lib.compile_rules(rules_bytes)
            compiled_json = self._c_string_to_python(result_ptr)
            
            # Verify result is not an error
            if compiled_json.startswith('{"error"'):
                logger.error(f"Rust compilation failed: {compiled_json}")
                self.is_available = False
                return False
            
            self.compiled_rules_json = compiled_json
            logger.info(f"Successfully pre-compiled {len(rules)} rules")
            return True
        
        except Exception as e:
            logger.error(f"Error pre-compiling rules: {e}")
            self.is_available = False
            return False
    
    def evaluate_funds_batch(self, funds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Evaluate multiple funds in parallel using Rust.
        
        Args:
            funds: List of fund data dictionaries
        
        Returns:
            List of violations (from Rust if available, Python fallback otherwise)
        """
        if not self.is_available or not self.original_rules_json:
            logger.debug("Using Python fallback for batch evaluation")
            if self.fallback_engine:
                return self.fallback_engine.evaluate_funds_batch(funds)
            return []
        
        try:
            funds_json = json.dumps(funds)
            funds_bytes = funds_json.encode('utf-8')
            rules_bytes = self.original_rules_json.encode('utf-8')  # Use ORIGINAL rules
            
            logger.debug(f"Evaluating {len(funds)} funds in Rust (parallel)...")
            
            result_ptr = self.lib.evaluate_funds_batch_ffi(funds_bytes, rules_bytes)
            violations_json = self._c_string_to_python(result_ptr)
            
            violations = json.loads(violations_json)
            logger.info(f"Evaluated {len(funds)} funds, found {len(violations)} violations")
            return violations
        
        except Exception as e:
            logger.error(f"Error in Rust batch evaluation: {e}. Falling back to Python.")
            self.is_available = False
            if self.fallback_engine:
                return self.fallback_engine.evaluate_funds_batch(funds)
            return []
    
    def evaluate_fund(self, fund: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Evaluate a single fund using Rust.
        
        Args:
            fund: Fund data dictionary
        
        Returns:
            List of violations (from Rust if available, Python fallback otherwise)
        """
        if not self.is_available or not self.original_rules_json:
            logger.debug("Using Python fallback for single fund evaluation")
            if self.fallback_engine:
                return self.fallback_engine.evaluate_fund(fund)
            return []
        
        try:
            fund_json = json.dumps(fund)
            fund_bytes = fund_json.encode('utf-8')
            rules_bytes = self.original_rules_json.encode('utf-8')  # Use ORIGINAL rules
            
            result_ptr = self.lib.evaluate_fund_ffi(fund_bytes, rules_bytes)
            violations_json = self._c_string_to_python(result_ptr)
            
            violations = json.loads(violations_json)
            return violations
        
        except Exception as e:
            logger.error(f"Error in Rust single fund evaluation: {e}. Falling back to Python.")
            self.is_available = False
            if self.fallback_engine:
                return self.fallback_engine.evaluate_fund(fund)
            return []
    
    def get_status(self) -> Dict[str, Any]:
        """Get Rust wrapper status"""
        return {
            "available": self.is_available,
            "dll_path": self.dll_path,
            "compiled_rules_cached": self.compiled_rules_json is not None,
            "has_fallback": self.fallback_engine is not None,
        }


class HybridRulesEngine:
    """
    Hybrid rules engine that uses Rust when available, Python fallback otherwise.
    
    This is the main interface for the compliance system.
    """
    
    def __init__(self, python_engine, use_rust: bool = True):
        """
        Initialize hybrid engine.
        
        Args:
            python_engine: Python RulesEngine fallback
            use_rust: Whether to try using Rust
        """
        self.python_engine = python_engine
        self.rust_wrapper: Optional[RulesEngineRustWrapper] = None
        
        if use_rust:
            self.rust_wrapper = RulesEngineRustWrapper(fallback_engine=python_engine)
            if self.rust_wrapper.is_available:
                logger.info("Hybrid engine initialized with Rust acceleration")
            else:
                logger.info("Hybrid engine using Python fallback (Rust not available)")
        else:
            logger.info("Hybrid engine using Python only (Rust disabled)")
    
    async def initialize(self, rules: List[Dict[str, Any]]):
        """Initialize rules (compile in Rust if available)"""
        await self.python_engine.load_rules()
        
        if self.rust_wrapper and self.rust_wrapper.is_available:
            # Get rules from Python engine
            rules_data = list(self.python_engine._rule_cache.values())
            for rule_dict in rules_data:
                rule_dict["id"] = list(self.python_engine._rule_cache.keys())[
                    rules_data.index(rule_dict)
                ]
            
            self.rust_wrapper.compile_rules(rules_data)
    
    async def evaluate_fund(self, fund_id: str, fund_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Evaluate fund (use Rust if available)"""
        if self.rust_wrapper and self.rust_wrapper.is_available:
            return self.rust_wrapper.evaluate_fund(fund_data)
        else:
            return await self.python_engine.evaluate_fund(fund_id, fund_data)
    
    async def evaluate_funds_batch(self, funds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Evaluate batch of funds (use Rust parallel if available)"""
        if self.rust_wrapper and self.rust_wrapper.is_available:
            return self.rust_wrapper.evaluate_funds_batch(funds)
        else:
            # Fallback to Python sequential
            violations = []
            for fund in funds:
                fund_violations = await self.python_engine.evaluate_fund(
                    fund.get("fund_id", "UNKNOWN"),
                    fund
                )
                violations.extend(fund_violations)
            return violations
    
    def get_engine_info(self) -> Dict[str, Any]:
        """Get information about which engine is being used"""
        if self.rust_wrapper:
            return {
                "type": "hybrid",
                "rust_status": self.rust_wrapper.get_status(),
                "python_available": True,
            }
        else:
            return {
                "type": "python_only",
                "rust_status": None,
                "python_available": True,
            }


# ============================================================================
# Convenience functions for testing
# ============================================================================

def test_rust_loading():
    """Test Rust library loading"""
    print("Testing Rust library loading...")
    wrapper = RulesEngineRustWrapper()
    status = wrapper.get_status()
    
    print(f"  Available: {status['available']}")
    print(f"  DLL Path: {status['dll_path']}")
    print(f"  Compiled Rules: {status['compiled_rules_cached']}")
    print(f"  Has Fallback: {status['has_fallback']}")
    
    return status['available']


def test_rust_compilation(rules: List[Dict[str, Any]]) -> bool:
    """Test rule compilation"""
    print(f"Testing Rust rule compilation ({len(rules)} rules)...")
    wrapper = RulesEngineRustWrapper()
    
    if not wrapper.is_available:
        print("  ❌ Rust not available")
        return False
    
    success = wrapper.compile_rules(rules)
    
    if success:
        print(f"  ✓ Compiled {len(rules)} rules successfully")
    else:
        print(f"  ❌ Compilation failed")
    
    return success


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    
    print("=" * 80)
    print("RUST RULES ENGINE WRAPPER - DIAGNOSTIC")
    print("=" * 80)
    print()
    
    # Test 1: Library loading
    available = test_rust_loading()
    print()
    
    # Test 2: Compilation (if available)
    if available:
        sample_rules = [
            {
                "id": "TEST_RULE_001",
                "title": "Test Rule",
                "condition": "holdings.max_sector_holding > 0.30",
                "severity": "high",
                "confidence_threshold": 0.95,
                "applicability": ["equity_fund"],
                "exclusions": [],
                "region": "SEBI",
            }
        ]
        test_rust_compilation(sample_rules)
    
    print()
    print("=" * 80)
    print("Diagnostic complete. Check logs above for details.")
    print("=" * 80)
