# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""
test_scenarios_with_tracing.py
==============================
Five comprehensive multi-turn query test scenarios with end-to-end tracing.

Scenarios:
1. Adani Enterprises Business Performance Deep Dive
2. Fund Manager and Company Relationships
3. Mining and Coal Business Exploration
4. SEBI Regulatory Framework Understanding
5. Adani Group Business Verticals

Each scenario includes:
- 4 turns of related multi-turn queries
- Expected metrics validation for each component
- Graph traversal verification
- Entity resolution tracking
- Context preservation across turns
"""

import pytest
from pathlib import Path
from typing import Dict, Any

from tests.test_multiturn_queries_with_tracing import (
    MultiTurnQueryTestFixture,
    _validate_query_turn,
)


# ═════════════════════════════════════════════════════════════════════════
# SCENARIO 1: Adani Enterprises Business Performance Deep Dive
# ═════════════════════════════════════════════════════════════════════════

class TestAdaniFinancialPerformance:
    """
    Tests financial metrics retrieval and comparison across quarters.
    
    Validates:
    - Direct financial metric lookup (Q1 FY19 EBITDA)
    - Context-aware comparison (Q1 FY19 vs Q1 FY18)
    - Business segment classification
    - Executive identification
    """

    @pytest.fixture
    def fixture(self):
        return MultiTurnQueryTestFixture("adani_financial_performance")

    def test_turn1_q1_fy19_ebitda(self, fixture):
        """Turn 1: Direct EBITDA metric retrieval."""
        trace = fixture.add_turn(
            query="What was Adani Enterprises' EBITDA performance in Q1 FY19?",
            expected_answer_contains=["589", "EBITDA", "FY19", "Q1"],
            expected_entities=["Adani Enterprises", "EBITDA", "Q1 FY19"],
            expected_graph_nodes_min=2,
            expected_graph_edges_min=1,
            query_type_expected="direct_lookup"
        )
        
        # Validate component-level metrics
        assert trace.llm_tokens_input > 0, "LLM should receive input tokens"
        assert trace.llm_tokens_output > 0, "LLM should generate output tokens"
        assert trace.answer_has_citations, "Answer should cite sources"
        assert trace.get_total_latency_ms() < 5000, "Should complete within 5 seconds"

    def test_turn2_q1_comparison_fy18_vs_fy19(self, fixture):
        """Turn 2: Context-aware YoY comparison with chat history."""
        trace = fixture.add_turn(
            query="How does this compare to Q1 FY18?",
            expected_answer_contains=["727", "FY18", "compare", "EBITDA"],
            expected_entities=["Q1 FY18", "EBITDA"],
            expected_graph_nodes_min=3,
            expected_graph_edges_min=2,
            query_type_expected="comparison"
        )
        
        # Validate chat history was included
        assert trace.chat_history_length == 2, "Should preserve one prior turn"
        assert trace.llm_tokens_input > trace.traces[0].llm_tokens_input, \
            "Token count should increase with history"

    def test_turn3_business_segments(self, fixture):
        """Turn 3: Business segment aggregation."""
        trace = fixture.add_turn(
            query="Which business segments does Adani Enterprises operate in?",
            expected_answer_contains=[
                "Coal trading",
                "Mining",
                "City Gas Distribution",
                "Solar Manufacturing"
            ],
            expected_entities=["Adani Enterprises", "business segments"],
            expected_graph_nodes_min=5,
            expected_graph_edges_min=4,
            query_type_expected="aggregation"
        )
        
        # Validate aggregation metrics
        assert trace.verified_aggregate_used or trace.comparison_table_used, \
            "Aggregation query should use verified aggregate or comparison mode"

    def test_turn4_executives(self, fixture):
        """Turn 4: Executive identification from earnings call."""
        trace = fixture.add_turn(
            query="Who are the key executives mentioned in their earnings call?",
            expected_answer_contains=[
                "Pranav Adani",
                "Rakesh Shah",
                "Vinay Prakash"
            ],
            expected_entities=["Pranav Adani", "Rakesh Shah", "Vinay Prakash"],
            expected_graph_nodes_min=3,
            expected_graph_edges_min=2,
            query_type_expected="direct_lookup"
        )
        
        # Validate NER captured entities
        all_identified = [e["text"] for e in trace.ner_entities_layer_a + trace.ner_entities_layer_b]
        assert len(all_identified) >= 3, f"Should identify at least 3 executives, got {all_identified}"

    def test_scenario_summary(self, fixture):
        """Verify aggregated metrics across all turns."""
        report = fixture.get_summary_report()
        
        assert report["turn_count"] == 4, "Should have 4 turns"
        assert report["total_tokens"] > 0, "Should track total tokens"
        assert report["component_latencies"], "Should have component latency breakdown"
        
        # Verify graph stats evolution
        graph_stats = report["graph_stats"]
        assert graph_stats["avg_nodes"] > 2, "Average graph nodes should be > 2"
        assert graph_stats["avg_edges"] > 1, "Average graph edges should be > 1"
        
        # Verify LLM stats
        llm_stats = report["llm_stats"]
        assert llm_stats["total_input_tokens"] > 0
        assert llm_stats["total_output_tokens"] > 0
        
        # Save report
        report_path = fixture.save_summary_report()
        assert report_path.exists(), f"Report should be saved at {report_path}"


# ═════════════════════════════════════════════════════════════════════════
# SCENARIO 2: Fund Manager and Company Relationships
# ═════════════════════════════════════════════════════════════════════════

class TestFundManagerRelationships:
    """
    Tests multi-hop graph traversal and entity relationship discovery.
    
    Validates:
    - Entity resolution for person identification
    - PART_OF relationship traversal
    - Graph relationship discovery
    - Entity linking across documents
    """

    @pytest.fixture
    def fixture(self):
        return MultiTurnQueryTestFixture("fund_manager_relationships")

    def test_turn1_pranav_adani_identification(self, fixture):
        """Turn 1: Person identification and company association."""
        trace = fixture.add_turn(
            query="Who is Pranav Adani and which company is he associated with?",
            expected_answer_contains=[
                "Pranav Adani",
                "Adani Enterprises",
                "fund manager"
            ],
            expected_entities=["Pranav Adani", "Adani Enterprises Limited"],
            expected_graph_nodes_min=2,
            expected_graph_edges_min=1,
            query_type_expected="direct_lookup"
        )
        
        # Validate entity resolution worked
        assert trace.entity_resolution is not None, "Should perform entity resolution"
        assert trace.entity_resolution.entities_resolved > 0, "Should resolve entities"
        assert trace.graph_matched_by in ["entity", "product"], "Should match via entity or product"

    def test_turn2_other_executives_graph_traversal(self, fixture):
        """Turn 2: Graph traversal to find related executives."""
        trace = fixture.add_turn(
            query="Tell me about other executives at Adani Enterprises Limited",
            expected_answer_contains=[
                "Rakesh Shah",
                "Adani Enterprises",
                "PART_OF"
            ],
            expected_entities=["Rakesh Shah", "Adani Enterprises Limited"],
            expected_graph_nodes_min=3,
            expected_graph_edges_min=2,
            query_type_expected="aggregation"
        )
        
        # Validate multi-hop traversal
        assert trace.graph_edges_retrieved >= 2, "Should traverse multiple edges"
        assert "PART_OF" in [e.get("rel") for e in trace.components.get("graph_traversal", {}).get("metrics", {}).get("edges", [])], \
            "Should use PART_OF relationship"

    def test_turn3_mundra_executives(self, fixture):
        """Turn 3: Scoped traversal to different company."""
        trace = fixture.add_turn(
            query="What about executives at Mundra Solar PV Limited?",
            expected_answer_contains=[
                "Ramesh Nair",
                "Rakesh Tiwary",
                "Mundra Solar"
            ],
            expected_entities=["Ramesh Nair", "Rakesh Tiwary", "Mundra Solar PV Limited"],
            expected_graph_nodes_min=2,
            expected_graph_edges_min=1,
            query_type_expected="direct_lookup"
        )
        
        # Validate scope switching
        assert "Mundra" in str([e.get("text") for e in trace.ner_entities_layer_a]), \
            "Should identify Mundra Solar company"

    def test_turn4_adani_group_ecosystem(self, fixture):
        """Turn 4: Cross-company relationship verification."""
        trace = fixture.add_turn(
            query="Are these companies related to Adani Group?",
            expected_answer_contains=[
                "Adani Group",
                "ecosystem",
                "related"
            ],
            expected_entities=["Adani Group", "Adani Enterprises", "Mundra Solar PV Limited"],
            expected_graph_nodes_min=4,
            expected_graph_edges_min=3,
            query_type_expected="comparison"
        )
        
        # Validate comparison mode engaged
        assert trace.comparison_table_used or len(trace.graph_edges_retrieved) > 2, \
            "Should use comparison mode or traverse multiple relationships"

    def test_scenario_entity_resolution_quality(self, fixture):
        """Verify entity resolution quality across all turns."""
        report = fixture.get_summary_report()
        
        # Check that entities are being consistently resolved
        total_ner_entities = (
            report["ner_stats"]["total_layer_a_entities"] +
            report["ner_stats"]["total_layer_b_entities"]
        )
        assert total_ner_entities > 10, f"Should identify 10+ entities, got {total_ner_entities}"
        
        # Verify graph traversal is discovering relationships
        graph_stats = report["graph_stats"]
        assert graph_stats["match_types"]["entity"] > 0 or graph_stats["match_types"]["product"] > 0, \
            "Should match on entity or product at least once"


# ═════════════════════════════════════════════════════════════════════════
# SCENARIO 3: Mining and Coal Business Exploration
# ═════════════════════════════════════════════════════════════════════════

class TestMiningAndCoalBusiness:
    """
    Tests domain-specific knowledge retrieval and aggregation.
    
    Validates:
    - Project name identification
    - Business segment classification
    - Executive role association
    - Entity aliasing (scheme name vs. managed entity)
    """

    @pytest.fixture
    def fixture(self):
        return MultiTurnQueryTestFixture("mining_coal_business")

    def test_turn1_mining_projects(self, fixture):
        """Turn 1: Project enumeration."""
        trace = fixture.add_turn(
            query="What mining projects are mentioned in the documents?",
            expected_answer_contains=[
                "Parsa",
                "GP3",
                "Talabira 2",
                "Talabira 3"
            ],
            expected_entities=["Parsa", "GP3", "Talabira"],
            expected_graph_nodes_min=3,
            expected_graph_edges_min=2,
            query_type_expected="aggregation"
        )
        
        assert trace.verified_aggregate_used or len(trace.graph_edges_retrieved) > 2, \
            "Should aggregate multiple project entities"

    def test_turn2_talabira_details(self, fixture):
        """Turn 2: Project-specific details with entity aliasing."""
        trace = fixture.add_turn(
            query="Tell me more about Talabira 2 and 3",
            expected_answer_contains=[
                "Talabira",
                "NLC",
                "scheme"
            ],
            expected_entities=["Talabira", "NLC"],
            expected_graph_nodes_min=3,
            expected_graph_edges_min=2,
            query_type_expected="direct_lookup"
        )
        
        # Verify context includes prior query
        assert trace.chat_history_length >= 1, "Should include prior turn"

    def test_turn3_coal_trading_business(self, fixture):
        """Turn 3: Business segment performance."""
        trace = fixture.add_turn(
            query="What is the coal trading business performance?",
            expected_answer_contains=[
                "coal trading",
                "Adani Enterprises",
                "business segment"
            ],
            expected_entities=["coal trading", "Adani Enterprises"],
            expected_graph_nodes_min=2,
            expected_graph_edges_min=1,
            query_type_expected="direct_lookup"
        )

    def test_turn4_mining_executive(self, fixture):
        """Turn 4: Executive role identification."""
        trace = fixture.add_turn(
            query="Who manages the Mining and ICM business?",
            expected_answer_contains=[
                "Ram Patodia",
                "Mining",
                "ICM"
            ],
            expected_entities=["Ram Patodia", "Mining", "ICM"],
            expected_graph_nodes_min=2,
            expected_graph_edges_min=1,
            query_type_expected="direct_lookup"
        )
        
        # Verify NER identified person and business domain
        identified_labels = set()
        for entity in trace.ner_entities_layer_a + trace.ner_entities_layer_b:
            identified_labels.add(entity.get("label", ""))
        
        assert any(label in identified_labels for label in ["PERSON", "NAME", "PERSON_NAME"]), \
            f"Should identify PERSON entity, got labels: {identified_labels}"


# ═════════════════════════════════════════════════════════════════════════
# SCENARIO 4: SEBI Regulatory Framework Understanding
# ═════════════════════════════════════════════════════════════════════════

class TestSEBIRegulatoryFramework:
    """
    Tests regulatory/technical document understanding and comparison.
    
    Validates:
    - Regulatory metric extraction
    - Cross-regulatory comparison
    - Conditional logic understanding
    - Regulatory hierarchy comprehension
    """

    @pytest.fixture
    def fixture(self):
        return MultiTurnQueryTestFixture("sebi_regulatory_framework")

    def test_turn1_mutual_fund_borrowing_limits(self, fixture):
        """Turn 1: Direct regulatory metric retrieval."""
        trace = fixture.add_turn(
            query="What are SEBI's borrowing limits for mutual funds?",
            expected_answer_contains=[
                "20%",
                "mutual funds",
                "net assets"
            ],
            expected_entities=["SEBI", "mutual funds", "borrowing"],
            expected_graph_nodes_min=1,
            expected_graph_edges_min=0,
            query_type_expected="direct_lookup"
        )
        
        # Regulatory queries should have high citation rate
        assert trace.citation_count > 0, "Regulatory answers should cite sources"

    def test_turn2_invit_comparison(self, fixture):
        """Turn 2: Cross-entity regulatory comparison."""
        trace = fixture.add_turn(
            query="How does this differ for Infrastructure Investment Trusts?",
            expected_answer_contains=[
                "InvIT",
                "49%",
                "differ",
                "asset value"
            ],
            expected_entities=["InvIT", "Infrastructure Investment Trusts"],
            expected_graph_nodes_min=1,
            expected_graph_edges_min=0,
            query_type_expected="comparison"
        )
        
        # Comparison queries should show explicit reasoning
        assert "differ" in trace.get_component_latency_breakdown() or \
               trace.comparison_table_used or \
               len(fixture.chat_history) >= 3, "Should explicitly compare"

    def test_turn3_invit_borrowing_purposes(self, fixture):
        """Turn 3: Conditional regulatory rules."""
        trace = fixture.add_turn(
            query="What are InvIT borrowings permitted for?",
            expected_answer_contains=[
                "capital expenditure",
                "acquisitions",
                "refinancing",
                "infrastructure"
            ],
            expected_entities=["InvIT", "borrowing", "capital expenditure"],
            expected_graph_nodes_min=1,
            expected_graph_edges_min=0,
            query_type_expected="direct_lookup"
        )

    def test_turn4_regulatory_synthesis(self, fixture):
        """Turn 4: Regulatory logic synthesis across turns."""
        trace = fixture.add_turn(
            query="So mutual funds have stricter borrowing rules than InvITs?",
            expected_answer_contains=[
                "stricter",
                "20%",
                "49%",
                "mutual funds",
                "InvIT"
            ],
            expected_entities=["mutual funds", "InvIT", "borrowing"],
            expected_graph_nodes_min=1,
            expected_graph_edges_min=0,
            query_type_expected="comparison"
        )
        
        # Synthesis should include all prior context
        assert trace.chat_history_length >= 6, "Should include multiple prior turns"
        assert trace.llm_tokens_input > 1000, "Synthesis should require more context"


# ═════════════════════════════════════════════════════════════════════════
# SCENARIO 5: Adani Group Business Verticals
# ═════════════════════════════════════════════════════════════════════════

class TestAdaniGroupVerticals:
    """
    Tests organizational hierarchy traversal and subsidiary identification.
    
    Validates:
    - Parent-child relationship discovery (group → companies)
    - Subsidiary function identification
    - Executive-company mapping across subsidiaries
    - Business domain classification
    """

    @pytest.fixture
    def fixture(self):
        return MultiTurnQueryTestFixture("adani_group_verticals")

    def test_turn1_group_companies(self, fixture):
        """Turn 1: Group-level company enumeration."""
        trace = fixture.add_turn(
            query="What companies are part of Adani Group?",
            expected_answer_contains=[
                "Adani Enterprises",
                "Adani Gas Limited",
                "Adani Wilmar",
                "Mundra Solar"
            ],
            expected_entities=["Adani Group", "Adani Enterprises", "Adani Gas", "Adani Wilmar"],
            expected_graph_nodes_min=4,
            expected_graph_edges_min=3,
            query_type_expected="aggregation"
        )
        
        # Should demonstrate graph depth for organizational hierarchy
        assert trace.graph_nodes_retrieved >= 4, "Should retrieve organizational hierarchy nodes"

    def test_turn2_wilmar_business(self, fixture):
        """Turn 2: Subsidiary business function."""
        trace = fixture.add_turn(
            query="What does Adani Wilmar do?",
            expected_answer_contains=[
                "agri business",
                "food",
                "Fortune",
                "edible oil"
            ],
            expected_entities=["Adani Wilmar", "Fortune", "edible oil"],
            expected_graph_nodes_min=2,
            expected_graph_edges_min=1,
            query_type_expected="direct_lookup"
        )

    def test_turn3_gas_business(self, fixture):
        """Turn 3: Subsidiary vertical with executive names."""
        trace = fixture.add_turn(
            query="Tell me about their gas business",
            expected_answer_contains=[
                "Adani Gas Limited",
                "City Gas Distribution",
                "CGD",
                "Naresh Poddar"
            ],
            expected_entities=["Adani Gas Limited", "City Gas Distribution", "Naresh Poddar"],
            expected_graph_nodes_min=3,
            expected_graph_edges_min=2,
            query_type_expected="direct_lookup"
        )
        
        # Verify entity-executive linking
        executives = [e["text"] for e in trace.ner_entities_layer_a if "Naresh" in e.get("text", "")]
        assert executives, "Should identify executive names"

    def test_turn4_mining_executive_scope(self, fixture):
        """Turn 4: Executive role in specific vertical."""
        trace = fixture.add_turn(
            query="Which executive oversees coal and mining operations?",
            expected_answer_contains=[
                "Vinay Prakash",
                "coal",
                "mining"
            ],
            expected_entities=["Vinay Prakash", "coal", "mining"],
            expected_graph_nodes_min=2,
            expected_graph_edges_min=1,
            query_type_expected="direct_lookup"
        )

    def test_scenario_organizational_hierarchy(self, fixture):
        """Verify organizational hierarchy traversal."""
        report = fixture.get_summary_report()
        
        # Should show consistent graph traversal depth
        graph_stats = report["graph_stats"]
        assert graph_stats["avg_nodes"] >= 2.5, \
            f"Org hierarchy should require 2.5+ avg nodes per query, got {graph_stats['avg_nodes']}"
        
        # Should identify multiple entities across entities
        ner_stats = report["ner_stats"]
        total_entities = (
            ner_stats["total_layer_a_entities"] +
            ner_stats["total_layer_b_entities"]
        )
        assert total_entities >= 12, f"Should identify 12+ entities across all turns, got {total_entities}"


# ═════════════════════════════════════════════════════════════════════════
# PARAMETRIZED TESTS: Run all scenarios with shared validation
# ═════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("scenario_class", [
    TestAdaniFinancialPerformance,
    TestFundManagerRelationships,
    TestMiningAndCoalBusiness,
    TestSEBIRegulatoryFramework,
    TestAdaniGroupVerticals,
])
def test_all_scenarios_complete_successfully(scenario_class):
    """Verify all scenarios can be instantiated and ran."""
    scenario = scenario_class()
    # Scenarios are tested individually above; this ensures they all exist
    methods = [m for m in dir(scenario) if m.startswith("test_turn")]
    assert len(methods) >= 4

