#!/usr/bin/env python3
"""
Setup Verification Script

Checks that the codynamic-book-machine environment is properly configured.
Verifies:
- Python dependencies
- API keys
- Directory structure
- Basic functionality

Usage:
    python verify_setup.py
"""

import sys
from pathlib import Path

def check_python_version():
    """Verify Python version"""
    print("Checking Python version...")
    if sys.version_info < (3, 8):
        print("  ❌ Python 3.8+ required")
        return False
    print(f"  ✅ Python {sys.version_info.major}.{sys.version_info.minor}")
    return True


def check_dependencies():
    """Check for required packages"""
    print("\nChecking dependencies...")
    
    required = {
        "yaml": "pyyaml",
        "openai": "openai",
        "anthropic": "anthropic"
    }
    
    missing = []
    for module, package in required.items():
        try:
            __import__(module)
            print(f"  ✅ {package}")
        except ImportError:
            print(f"  ❌ {package} - Install with: pip install {package}")
            missing.append(package)
    
    return len(missing) == 0


def check_api_keys():
    """Check for API keys"""
    print("\nChecking API keys...")
    
    import os
    
    openai_key = os.getenv("KEY_OPENAI_API")
    anthropic_key = os.getenv("KEY_ANTHROPIC_API") or os.getenv("ANTHROPIC_API_KEY")
    
    has_key = False
    
    if openai_key:
        print(f"  ✅ KEY_OPENAI_API found (length: {len(openai_key)})")
        has_key = True
    else:
        print("  ⚠️  KEY_OPENAI_API not set")
    
    if anthropic_key:
        print(f"  ✅ KEY_ANTHROPIC_API found (length: {len(anthropic_key)})")
        has_key = True
    else:
        print("  ⚠️  KEY_ANTHROPIC_API not set")
    
    if not has_key:
        print("\n  ❌ At least one API key required")
        print("     Set with: export KEY_OPENAI_API='your-key'")
        print("            or: export KEY_ANTHROPIC_API='your-key'")
        return False
    
    return True


def check_directory_structure():
    """Verify directory structure"""
    print("\nChecking directory structure...")
    
    required_dirs = [
        "scripts/api",
        "scripts/agents",
        "scripts/agents/agent_definitions",
        "tests",
        "data",
        "examples"
    ]
    
    all_exist = True
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists():
            print(f"  ✅ {dir_path}/")
        else:
            print(f"  ❌ {dir_path}/ - Missing!")
            all_exist = False
    
    return all_exist


def test_provider_import():
    """Test that provider system works"""
    print("\nTesting provider system...")
    
    try:
        sys.path.insert(0, str(Path.cwd()))
        from scripts.api import LLMProvider, Message, get_provider_with_fallback
        print("  ✅ Provider imports successful")
        
        # Try to create a provider
        try:
            provider = get_provider_with_fallback(["openai", "anthropic"])
            print(f"  ✅ Provider initialized: {provider.get_provider_name()}")
            return True
        except Exception as e:
            print(f"  ⚠️  Provider initialization failed: {e}")
            print("     (This is OK if API keys aren't set)")
            return True
            
    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        return False


def test_agent_import():
    """Test that agent system works"""
    print("\nTesting agent system...")
    
    try:
        from scripts.agents.agent_controller import AgentController
        print("  ✅ Agent controller import successful")
        return True
    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        return False


def run_basic_test():
    """Run a basic functionality test"""
    print("\nRunning basic functionality test...")
    
    try:
        # Create a minimal test
        from scripts.api import Message
        msg = Message(role="user", content="test")
        print(f"  ✅ Message creation works")
        
        return True
    except Exception as e:
        print(f"  ❌ Test failed: {e}")
        return False


def main():
    print("=" * 60)
    print("Codynamic Book Machine - Setup Verification")
    print("=" * 60)
    
    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("API Keys", check_api_keys),
        ("Directory Structure", check_directory_structure),
        ("Provider System", test_provider_import),
        ("Agent System", test_agent_import),
        ("Basic Functionality", run_basic_test),
    ]
    
    results = []
    for name, check_func in checks:
        result = check_func()
        results.append((name, result))
    
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    all_passed = True
    for name, result in results:
        status = "✅" if result else "❌"
        print(f"{status} {name}")
        if not result:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\n🎉 Setup verification PASSED!")
        print("\nNext steps:")
        print("1. Run tests: python -m pytest tests/ -v")
        print("2. Try demo: python examples/simple_agent_demo.py")
        print("3. Read PROGRESS.md for development roadmap")
    else:
        print("\n⚠️  Some checks failed. Please fix the issues above.")
        print("\nFor help:")
        print("- Install dependencies: pip install -r requirements.txt")
        print("- Set API keys: export KEY_OPENAI_API='your-key'")
        print("- Check PROGRESS.md for detailed setup instructions")
    
    print()
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
