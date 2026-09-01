# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""Test proving collision-free canonical source and document identity generation."""
from app.contracts.identity import generate_document_id, generate_source_id


def test_source_id_collision_prevention_across_directories():
    path_a = "data/regulatory/circular_2017.pdf"
    path_b = "data/compliance/circular_2017.pdf"

    source_id_a = generate_source_id(path_a, namespace="corpus")
    source_id_b = generate_source_id(path_b, namespace="corpus")

    assert source_id_a != source_id_b, "Files in different directories must have distinct source_ids"

    doc_id_a = generate_document_id(source_id_a)
    doc_id_b = generate_document_id(source_id_b)

    assert doc_id_a != doc_id_b, "Files in different directories must have distinct document_ids"


def test_source_id_case_and_slash_normalization():
    path_win = "data\\Regulatory\\Circular_2017.PDF"
    path_posix = "data/regulatory/circular_2017.pdf"

    source_id_win = generate_source_id(path_win, namespace="corpus")
    source_id_posix = generate_source_id(path_posix, namespace="corpus")

    assert source_id_win == source_id_posix, "Windows backslashes and case differences must normalize identically"
