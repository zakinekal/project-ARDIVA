#!/usr/bin/env python
"""
Test script untuk verifikasi OCR integration
Menguji:
1. Fungsi helper bekerja dengan baik
2. Error handling untuk file yang tidak ada
3. Return value structure dari ekstrak_surat
"""

import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_imports():
    """Test semua imports berhasil"""
    print("\n=== TEST 1: Verifikasi Imports ===")
    try:
        from baca_surat import (
            ekstrak_surat, 
            extract_text_from_pdf,
            _get_ocr_reader,
            _has_text_layer,
            _preprocess_image,
            _extract_text_via_ocr
        )
        print("✓ Semua fungsi berhasil di-import")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False


def test_extract_nonexistent_file():
    """Test error handling untuk file yang tidak ada"""
    print("\n=== TEST 2: Error Handling (File Tidak Ada) ===")
    try:
        from baca_surat import ekstrak_surat
        
        result = ekstrak_surat("/path/yang/tidak/ada/file.pdf")
        
        # Check return structure
        required_keys = ["no_surat", "tanggal_surat", "pengirim", "perihal", 
                        "uraian_arsip", "jumlah", "kode_klas", "teks_lengkap", "butuh_ocr"]
        
        for key in required_keys:
            if key not in result:
                print(f"✗ Missing key in result: {key}")
                return False
        
        print(f"✓ Error handling OK, result structure valid")
        print(f"  - butuh_ocr flag: {result['butuh_ocr']}")
        print(f"  - uraian_arsip: {result['uraian_arsip'][:50]}...")
        return True
    except Exception as e:
        print(f"✗ Test failed: {e}")
        return False


def test_ocr_reader_lazy_load():
    """Test OCR reader lazy loading"""
    print("\n=== TEST 3: OCR Reader Lazy Loading ===")
    try:
        from baca_surat import _get_ocr_reader
        
        print("Calling _get_ocr_reader()...")
        reader = _get_ocr_reader()
        
        if reader is None:
            print("⚠ Tesseract runtime is not installed on this machine")
            return False
        
        reader_name = str(reader).lower()
        if "tesseract" not in reader_name and "tesseract" not in type(reader).__name__.lower():
            print(f"✗ Expected Tesseract backend, got: {type(reader).__name__}")
            return False

        print("✓ Tesseract backend loaded successfully")
        print(f"  - Backend name: {type(reader).__name__}")
        return True
    except Exception as e:
        print(f"✗ OCR Reader loading failed: {e}")
        return False


def test_preprocessing_function():
    """Test image preprocessing function"""
    print("\n=== TEST 4: Image Preprocessing Function ===")
    try:
        import cv2
        import numpy as np
        from baca_surat import _preprocess_image
        
        # Create dummy image (100x100 grayscale)
        dummy_image = np.random.randint(0, 256, (100, 100), dtype=np.uint8)
        
        result = _preprocess_image(dummy_image)
        
        if result is None:
            print("✗ Preprocessing returned None")
            return False
        
        if result.shape != dummy_image.shape:
            print(f"✗ Output shape mismatch: {result.shape} vs {dummy_image.shape}")
            return False
        
        print("✓ Image preprocessing OK")
        print(f"  - Input shape: {dummy_image.shape}")
        print(f"  - Output shape: {result.shape}")
        print(f"  - Output dtype: {result.dtype}")
        return True
    except Exception as e:
        print(f"✗ Preprocessing test failed: {e}")
        return False


def test_extract_text_from_pdf_signature():
    """Test extract_text_from_pdf returns correct number of values"""
    print("\n=== TEST 5: Extract PDF Function Signature ===")
    try:
        from baca_surat import extract_text_from_pdf
        
        # Call with non-existent file (should handle gracefully)
        result = extract_text_from_pdf("/nonexistent/file.pdf")
        
        if not isinstance(result, tuple) or len(result) != 3:
            print(f"✗ Expected 3-tuple, got {type(result)} with len {len(result)}")
            return False
        
        text, pages, butuh_ocr = result
        
        if not isinstance(text, str):
            print(f"✗ First element should be str, got {type(text)}")
            return False
        
        if not isinstance(pages, int):
            print(f"✗ Second element should be int, got {type(pages)}")
            return False
        
        if not isinstance(butuh_ocr, bool):
            print(f"✗ Third element should be bool, got {type(butuh_ocr)}")
            return False
        
        print("✓ Function signature correct (text, pages, butuh_ocr)")
        print(f"  - text: str (length={len(text)})")
        print(f"  - pages: int (value={pages})")
        print(f"  - butuh_ocr: bool (value={butuh_ocr})")
        return True
    except Exception as e:
        print(f"✗ Signature test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║           OCR INTEGRATION TEST SUITE                          ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    
    tests = [
        test_imports,
        test_extract_nonexistent_file,
        test_ocr_reader_lazy_load,
        test_preprocessing_function,
        test_extract_text_from_pdf_signature,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ Unexpected error in {test.__name__}: {e}")
            results.append(False)
    
    print("\n" + "═" * 70)
    print(f"SUMMARY: {sum(results)}/{len(results)} tests passed")
    print("═" * 70)
    
    if all(results):
        print("✓ All tests passed! OCR integration is ready.")
        return 0
    else:
        print("✗ Some tests failed. Please review output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
