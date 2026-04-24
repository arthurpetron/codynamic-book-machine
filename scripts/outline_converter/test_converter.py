"""
Test Suite for Outline Converter
Demonstrates conversion of various outline formats
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from converter import OutlineConverter


# Test input 1: Digital Symmetries (nested nodes format)
DIGITAL_SYMMETRIES_OUTLINE = """On the Closure of Compositional Hierarchies in Digital Symmetries

### Summary of Understanding
The outline presents a structured plan for a technical book examining the interplay of compositionality, closure properties, and symmetries in digital systems, drawing from category theory (operads, PROPs), Boolean function theory (clones, Post's lattice), and applications to hardware, software, and beyond (e.g., quantum, crypto, ML).

<node-singleton> Title Page(s)
<node-with-children> Front Matter
  Preface
    Motivation: compositionality, closure, and symmetry in digital systems
    Audience & prerequisites: discrete math, basic category theory, digital logic
  Notation & Conventions
    Symbol table and operations
  Methodological Protocol
    Claims-as-builds: theorems paired with executable artifacts/tests

<node-with-children> Chapters
  Part I: Foundations
    1. Orientation & Thesis: Closure of Compositional Hierarchies in Digital Symmetries
      Digital objects: Boolean domains, circuits, finite automata
      Symmetry: invariance under permutations and negations
      Composition: substitution, product, trace operations
    2. Operads, PROPs, and Symmetric Monoidal Foundations
      Operads: substitution, units, symmetric actions
      PROPs: circuits as morphisms; wiring diagrams
    3. Closure & Clones: Post's Lattice for Boolean Functions
      Closure operators; projections; clones
      Post's lattice: monotone, affine, self-dual classes
  Part II: Constructions and Modularity
    4. Hierarchical Modularity & Contracts
      Modules, interfaces, parameterization
      Hypergraph categories for open circuits
    5. Sequential Composition, Feedback, and Traces
      Mealy/Moore machines; traced categories
      Automata minimization
  Part III: Symmetries and Applications
    8. Symmetry Groups of Boolean Functions and Circuits
      Symmetric group actions; NPN equivalence
    9. Reliability, Noise, and Robust Closure
      Noisy gates, error-correcting codes

<node-singleton> Bibliography
<node-with-children> Back Matter
  Appendices
    A. Post's lattice cheat sheet
    B. Operad/PROP identities
  Glossary & Symbol Index
  Artifacts & Reproducibility
"""


# Test input 2: Quantum Categories (numbered hierarchy format)
QUANTUM_CATEGORIES_OUTLINE = """Quantum Categories: Diagrammatic Reasoning for Noncommutative Realities

Front matter
* Dedication: To diagrammatic innovators in quantum foundations.
* Foreword: By a fictional collaborator on noncommutative spaces.
* Preface: Detached summary of quantum diagrams and toposes.
* Acknowledgments: Credits to Coecke, Connes, Doering-Isham.
* Table of Contents: Chapter outlines.
* List of Symbols: Notation for string diagrams and sheaves.

Chapters
1. Foundations of Quantum Diagrams 
   1.1 Recalled Diagrammatic Methods 
      1.1.1 Coecke's Processes 
      1.1.2 String Diagram Basics 
   1.2 Noncommutative Geometry Fragments 
      1.2.1 Connes' Algebras 
      1.2.2 Spectral Triples Stored 
   1.3 Introduction to Topos Approaches
2. Categorical Tools for Quantum Spacetime 
   2.1 Functorial Semantics in Physics 
      2.1.1 Doering-Isham's Representations 
      2.1.2 Arrows as Quantities 
   2.2 Diagrammatic Reasoning Applied 
      2.2.1 Visualizing Noncommutativity 
      2.2.2 Entanglement Diagrams 
   2.3 Examples from Quantum Models
3. Novel Approaches to Realities 
   3.1 Merging Toposes and Geometry 
      3.1.1 Sheaf Foundations 
      3.1.2 Causal Structures 
   3.2 Spacetime as Categories 
      3.2.1 Noncommutative Extensions 
      3.2.2 Diagrammatic Proofs 
   3.3 Case Studies in Fragmented Quantum
4. Extensions and Applications 
   4.1 Quantum Computing Links 
      4.1.1 Protocol Semantics 
      4.1.2 Error Correction Notes 
   4.2 Limits of Diagrammatic Methods 
      4.2.1 Memorized Challenges 
      4.2.2 Future Research Items 
   4.3 Problems and Solutions

Back matter
* Appendix B: Diagram Construction Guide.
* References: CoeckeKissinger2017, Connes1994, Doering2007a, Doering2008.
* Index: Entries for "topos", "noncommutative", "diagram".
* About the Author: Hypothetical bio.
"""


def test_digital_symmetries_conversion():
    """Test conversion of Digital Symmetries outline."""
    print("\n" + "="*70)
    print("TEST 1: Digital Symmetries (Nested Nodes Format)")
    print("="*70)
    
    converter = OutlineConverter()
    
    try:
        result = converter.convert(
            DIGITAL_SYMMETRIES_OUTLINE,
            output_path='test_output_digital_symmetries.yaml',
            interactive=False
        )
        
        print("\n✅ Conversion successful!")
        print(f"\nFirst 50 lines of output:")
        print("-" * 70)
        lines = result.split('\n')
        for line in lines[:50]:
            print(line)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Conversion failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_quantum_categories_conversion():
    """Test conversion of Quantum Categories outline."""
    print("\n" + "="*70)
    print("TEST 2: Quantum Categories (Numbered Hierarchy Format)")
    print("="*70)
    
    converter = OutlineConverter()
    
    try:
        result = converter.convert(
            QUANTUM_CATEGORIES_OUTLINE,
            output_path='test_output_quantum_categories.yaml',
            interactive=False
        )
        
        print("\n✅ Conversion successful!")
        print(f"\nFirst 50 lines of output:")
        print("-" * 70)
        lines = result.split('\n')
        for line in lines[:50]:
            print(line)
        
        return True
        
    except Exception as e:
        print(f"\n❌ Conversion failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_format_detection():
    """Test automatic format detection."""
    print("\n" + "="*70)
    print("TEST 3: Format Detection")
    print("="*70)
    
    converter = OutlineConverter()
    
    # Test nested nodes
    format1 = converter.detect_format(DIGITAL_SYMMETRIES_OUTLINE)
    print(f"Digital Symmetries format: {format1}")
    assert format1 == 'nested_nodes', f"Expected 'nested_nodes', got '{format1}'"
    
    # Test numbered hierarchy
    format2 = converter.detect_format(QUANTUM_CATEGORIES_OUTLINE)
    print(f"Quantum Categories format: {format2}")
    assert format2 == 'numbered_hierarchy', f"Expected 'numbered_hierarchy', got '{format2}'"
    
    print("\n✅ Format detection working correctly!")
    return True


def run_all_tests():
    """Run all test cases."""
    print("\n" + "="*70)
    print("OUTLINE CONVERTER TEST SUITE")
    print("="*70)
    
    results = []
    
    # Test format detection
    results.append(('Format Detection', test_format_detection()))
    
    # Test conversions
    results.append(('Digital Symmetries', test_digital_symmetries_conversion()))
    results.append(('Quantum Categories', test_quantum_categories_conversion()))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        print("\n🎉 All tests passed!")
    else:
        print("\n⚠️  Some tests failed")
    
    return all_passed


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
