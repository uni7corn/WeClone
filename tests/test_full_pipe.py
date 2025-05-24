import pytest
from unittest import mock
import sys
import os
import shutil
import functools
import subprocess
import time
from typing import Union, Optional, cast
from weclone.utils.log import logger

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
PROJECT_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
server_process: Optional[subprocess.Popen] = None

test_logger = logger.bind()
test_logger.remove()
test_logger.add(
    sys.stderr,
    format="<yellow><b>{message}</b></yellow>",
    colorize=True,
    level="INFO",
)

def print_test_header(test_name: str):
    line_length = 100
    test_logger.info("\n" + "─" * line_length)
    title = f"  Testing Phase: {test_name}  "
    padding_total = line_length - len(title)
    padding_left = padding_total // 2
    padding_right = padding_total - padding_left
    test_logger.info(" " * padding_left + title + " " * padding_right)
    test_logger.info("─" * line_length)

def setup_make_dataset_test_data():
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    DATASET_CSV_DIR = os.path.join(PROJECT_ROOT, "dataset", "csv")
    
    TESTS_DIR = os.path.dirname(__file__)
    TEST_DATA_PERSON_DIR = os.path.join(TESTS_DIR, "tests_data", "test_person")

    os.makedirs(DATASET_CSV_DIR, exist_ok=True) 

    if os.path.exists(DATASET_CSV_DIR) and os.listdir(DATASET_CSV_DIR):
        if all(f.startswith('.') or f.lower() == 'readme.md' for f in os.listdir(DATASET_CSV_DIR)):
            for item_name in os.listdir(TEST_DATA_PERSON_DIR):
                source_item_path = os.path.join(TEST_DATA_PERSON_DIR, item_name)
                if os.path.isfile(source_item_path) and item_name.lower().endswith('.csv'):
                    destination_item_path = os.path.join(DATASET_CSV_DIR, item_name)
                    shutil.copy2(source_item_path, destination_item_path)
        

def run_cli_command(command: list[str], timeout: int | None = None, background: bool = False) -> Union[subprocess.CompletedProcess, subprocess.Popen]:
    """Execute a CLI command and return the result.
    
    Args:
        command: List of commands to execute.
        timeout: Timeout in seconds.
        background: Whether to run in the background.
        
    Returns:
        If background=True, returns a Popen object; otherwise, returns a CompletedProcess object.
    """
    env = os.environ.copy()
    env["WECLONE_CONFIG_PATH"] = "tests/full_pipe.jsonc" # Set environment variable

    if background:
        process = subprocess.Popen(
            [sys.executable, "-m", "weclone.cli"] + command,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
            cwd=PROJECT_ROOT_DIR,
            env=env
        )
        time.sleep(2)
        return process
    else:
        process = subprocess.run(
            [sys.executable, "-m", "weclone.cli"] + command,
            stderr=None,
            stdout=None,
            text=True,
            cwd=PROJECT_ROOT_DIR,  # Execute in the project root directory
            timeout=timeout,
            env=env  # Pass the modified environment variables
        )
        return process

@pytest.mark.order(1)
def test_cli_make_dataset():
    """Test the make-dataset command."""
    print_test_header("make-dataset")
    setup_make_dataset_test_data()
    result = run_cli_command(["make-dataset"])
    assert result.returncode == 0, "make-dataset command execution failed"

@pytest.mark.order(2)
def test_cli_train_sft():
    """Test the train-sft command."""
    print_test_header("train-sft")
    try:
        result = run_cli_command(["train-sft"]) 
        assert result.returncode == 0, "train-sft command failed or did not fail fast as expected"
    except subprocess.TimeoutExpired:
        test_logger.info("train-sft command terminated due to timeout, which is acceptable in testing, indicating the command has started execution.")
        pass
    except Exception as e:
        pytest.fail(f"An unexpected error occurred during train-sft command execution: {e}")

@pytest.mark.order(3)
def test_cli_webchat_demo():
    """Test the webchat-demo command."""
    print_test_header("webchat-demo")
    
    with mock.patch("weclone.eval.web_demo.main") as mock_main:
        mock_main.return_value = None
        try:
            result = run_cli_command(["webchat-demo"], timeout=5)
            assert result.returncode == 0, "webchat-demo command execution failed"
        except subprocess.TimeoutExpired:
            pass

@pytest.mark.order(4)
def test_cli_server():
    """Test the server command.
    
    Start the server in the background, without blocking subsequent tests.
    """
    print_test_header("server (background)")
    global server_process
    server_process = cast(subprocess.Popen, run_cli_command(["server"], background=True))
    assert server_process.poll() is None, "Server startup failed"
    test_logger.info("服务器已在后台启动")

@pytest.mark.order(5)
def test_cli_test_model():
    """Test the test-model command.
    
    Use the server for testing, and shut down the server after the test is complete.
    """
    print_test_header("test-model")
    try:
        result = run_cli_command(["test-model"])
        assert result.returncode == 0, "test-model command execution failed"
    finally:
        global server_process
        if server_process is not None and server_process.poll() is None:
            test_logger.info("测试完成，正在关闭服务器...")
            server_process.terminate()
            server_process.wait(timeout=5)
            if server_process.poll() is None:
                server_process.kill()  # Force kill if the process hasn't terminated
            test_logger.info("服务器已关闭")
