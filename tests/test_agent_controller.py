"""
Tests for Agent Controller

Run with: python -m pytest tests/test_agent_controller.py -v
Or: python tests/test_agent_controller.py
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import yaml
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.agents.agent_controller import AgentController, launch_agent_thread
from scripts.api import Message, LLMResponse


class TestAgentController(unittest.TestCase):
    """Test AgentController functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Create temporary directory for test data
        self.test_dir = tempfile.mkdtemp()
        self.data_root = Path(self.test_dir) / "data"
        self.data_root.mkdir(parents=True)
        
        # Create test agent definition
        self.agent_yaml_path = Path(self.test_dir) / "test_agent.yaml"
        self.test_agent_def = {
            "name": "test_agent",
            "role": "Test agent for unit testing",
            "tasks": [
                "Execute test actions",
                "Validate functionality"
            ],
            "permissions": [
                "read_test_data",
                "write_test_output"
            ],
            "actions": [
                {
                    "id": "test_action",
                    "description": "A test action",
                    "prompt_template": "Execute test action with context: {param1}"
                },
                {
                    "id": "simple_action",
                    "description": "Simple action without parameters",
                    "prompt_template": "Perform simple action"
                }
            ]
        }
        
        with open(self.agent_yaml_path, 'w') as f:
            yaml.dump(self.test_agent_def, f)
        
        # Create mock LLM provider
        self.mock_provider = Mock()
        self.mock_provider.get_provider_name.return_value = "mock"
        self.mock_provider.get_stats.return_value = {"call_count": 0}
    
    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.test_dir)
    
    def test_initialization(self):
        """Test basic controller initialization"""
        controller = AgentController(
            agent_yaml_path=str(self.agent_yaml_path),
            agent_id="test_001",
            provider=self.mock_provider,
            data_root=self.data_root
        )
        
        self.assertEqual(controller.agent_id, "test_001")
        self.assertEqual(controller.agent_def['name'], "test_agent")
        self.assertIsNotNone(controller.agent_state_dir)
        self.assertTrue(controller.agent_state_dir.exists())
    
    def test_load_agent_definition(self):
        """Test agent definition loading"""
        controller = AgentController(
            agent_yaml_path=str(self.agent_yaml_path),
            agent_id="test_002",
            provider=self.mock_provider,
            data_root=self.data_root
        )
        
        agent_def = controller.agent_def
        self.assertEqual(agent_def['name'], "test_agent")
        self.assertEqual(agent_def['role'], "Test agent for unit testing")
        self.assertEqual(len(agent_def['actions']), 2)
    
    def test_missing_agent_definition(self):
        """Test handling of missing agent definition"""
        with self.assertRaises(FileNotFoundError):
            AgentController(
                agent_yaml_path="/nonexistent/path.yaml",
                agent_id="test_003",
                provider=self.mock_provider,
                data_root=self.data_root
            )
    
    def test_build_system_prompt(self):
        """Test system prompt generation"""
        controller = AgentController(
            agent_yaml_path=str(self.agent_yaml_path),
            agent_id="test_004",
            provider=self.mock_provider,
            data_root=self.data_root
        )
        
        system_prompt = controller._build_system_prompt()
        
        self.assertIn("test_agent", system_prompt)
        self.assertIn("Test agent for unit testing", system_prompt)
        self.assertIn("Execute test actions", system_prompt)
        self.assertIn("read_test_data", system_prompt)
    
    def test_add_task(self):
        """Test task queue management"""
        controller = AgentController(
            agent_yaml_path=str(self.agent_yaml_path),
            agent_id="test_005",
            provider=self.mock_provider,
            data_root=self.data_root
        )
        
        initial_length = len(controller.task_queue)
        
        controller.add_task("test_action", {"param1": "value1"})
        
        self.assertEqual(len(controller.task_queue), initial_length + 1)
        
        task = controller.task_queue[-1]
        self.assertEqual(task['action_id'], "test_action")
        self.assertEqual(task['context']['param1'], "value1")
        self.assertIn('added_at', task)
    
    def test_execute_action(self):
        """Test action execution"""
        controller = AgentController(
            agent_yaml_path=str(self.agent_yaml_path),
            agent_id="test_006",
            provider=self.mock_provider,
            data_root=self.data_root
        )
        
        # Mock provider response
        mock_response = LLMResponse(
            content="Test response",
            model="test-model",
            provider="mock",
            tokens_used=50
        )
        self.mock_provider.call.return_value = mock_response
        
        # Execute action
        response = controller.execute_action(
            "test_action",
            {"param1": "test_value"}
        )
        
        self.assertEqual(response.content, "Test response")
        self.mock_provider.call.assert_called_once()
        
        # Verify messages passed to provider
        call_args = self.mock_provider.call.call_args
        messages = call_args[1]['messages']
        
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0].role, "system")
        self.assertEqual(messages[1].role, "user")
        self.assertIn("test_value", messages[1].content)
    
    def test_execute_invalid_action(self):
        """Test execution of non-existent action"""
        controller = AgentController(
            agent_yaml_path=str(self.agent_yaml_path),
            agent_id="test_007",
            provider=self.mock_provider,
            data_root=self.data_root
        )
        
        with self.assertRaises(ValueError):
            controller.execute_action("nonexistent_action")
    
    def test_run_next_task(self):
        """Test task execution from queue"""
        controller = AgentController(
            agent_yaml_path=str(self.agent_yaml_path),
            agent_id="test_008",
            provider=self.mock_provider,
            data_root=self.data_root
        )
        
        # Mock provider response
        mock_response = LLMResponse(
            content="Task completed",
            model="test-model",
            provider="mock"
        )
        self.mock_provider.call.return_value = mock_response
        
        # Add task and execute
        controller.add_task("simple_action")
        
        result = controller.run_next_task()
        
        self.assertTrue(result)
        self.assertEqual(len(controller.task_queue), 0)
    
    def test_run_next_task_empty_queue(self):
        """Test behavior with empty task queue"""
        controller = AgentController(
            agent_yaml_path=str(self.agent_yaml_path),
            agent_id="test_009",
            provider=self.mock_provider,
            data_root=self.data_root
        )
        
        result = controller.run_next_task()
        self.assertFalse(result)
    
    def test_receive_message(self):
        """Test message reception"""
        controller = AgentController(
            agent_yaml_path=str(self.agent_yaml_path),
            agent_id="test_010",
            provider=self.mock_provider,
            data_root=self.data_root
        )
        
        message = {
            "subject": "Test message",
            "from": "other_agent",
            "body": "Test content"
        }
        
        controller.receive_message(message)
        
        self.assertEqual(len(controller.message_inbox), 1)
        self.assertEqual(controller.message_inbox[0]['subject'], "Test message")
    
    def test_process_message(self):
        """Test message processing"""
        controller = AgentController(
            agent_yaml_path=str(self.agent_yaml_path),
            agent_id="test_011",
            provider=self.mock_provider,
            data_root=self.data_root
        )
        
        message = {
            "subject": "Task request",
            "from": "requester",
            "body": "action_id: test_action\ncontext:\n  param1: from_message"
        }
        
        controller.process_message(message)
        
        # Should have added task to queue
        self.assertGreater(len(controller.task_queue), 0)
    
    def test_task_persistence(self):
        """Test task queue persistence"""
        controller1 = AgentController(
            agent_yaml_path=str(self.agent_yaml_path),
            agent_id="test_012",
            provider=self.mock_provider,
            data_root=self.data_root
        )
        
        # Add tasks
        controller1.add_task("test_action", {"param1": "value1"})
        controller1.add_task("simple_action")
        
        # Create new controller with same ID - should load saved queue
        controller2 = AgentController(
            agent_yaml_path=str(self.agent_yaml_path),
            agent_id="test_012",
            provider=self.mock_provider,
            data_root=self.data_root
        )
        
        self.assertEqual(len(controller2.task_queue), 2)
    
    def test_get_stats(self):
        """Test statistics retrieval"""
        controller = AgentController(
            agent_yaml_path=str(self.agent_yaml_path),
            agent_id="test_013",
            provider=self.mock_provider,
            data_root=self.data_root
        )
        
        controller.add_task("test_action")
        
        stats = controller.get_stats()
        
        self.assertIn("agent_id", stats)
        self.assertIn("provider", stats)
        self.assertIn("task_queue_length", stats)
        self.assertEqual(stats['agent_id'], "test_013")
        self.assertEqual(stats['task_queue_length'], 1)
    
    def test_stop_mechanism(self):
        """Test graceful stop"""
        controller = AgentController(
            agent_yaml_path=str(self.agent_yaml_path),
            agent_id="test_014",
            provider=self.mock_provider,
            data_root=self.data_root
        )
        
        self.assertFalse(controller.running)
        
        controller.running = True
        self.assertTrue(controller.running)
        
        controller.stop()
        self.assertFalse(controller.running)


class TestAgentThreading(unittest.TestCase):
    """Test threaded agent execution"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_dir = tempfile.mkdtemp()
        self.data_root = Path(self.test_dir) / "data"
        self.data_root.mkdir(parents=True)
        
        self.agent_yaml_path = Path(self.test_dir) / "test_agent.yaml"
        agent_def = {
            "name": "thread_test_agent",
            "role": "Testing threaded execution",
            "actions": [
                {
                    "id": "quick_action",
                    "prompt_template": "Quick test"
                }
            ]
        }
        
        with open(self.agent_yaml_path, 'w') as f:
            yaml.dump(agent_def, f)
    
    def tearDown(self):
        """Clean up"""
        shutil.rmtree(self.test_dir)
    
    @patch('scripts.agents.agent_controller.get_provider')
    def test_launch_agent_thread(self, mock_get_provider):
        """Test agent launch in thread"""
        # Mock provider
        mock_provider = Mock()
        mock_provider.get_provider_name.return_value = "mock"
        mock_provider.get_stats.return_value = {"call_count": 0}
        mock_get_provider.return_value = mock_provider
        
        controller, thread = launch_agent_thread(
            agent_yaml_path=str(self.agent_yaml_path),
            agent_id="thread_001",
            data_root=self.data_root
        )
        
        # Give thread time to start
        import time
        time.sleep(0.1)
        
        self.assertIsInstance(controller, AgentController)
        self.assertTrue(thread.is_alive())
        self.assertTrue(controller.running)
        
        # Stop gracefully
        controller.stop()
        time.sleep(0.1)


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
