import httpx
import json
import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "deepseek-r1:latest"

def _extract_json(text: str) -> str:
    """
    Attempts to extract JSON from a string that might contain preamble/postamble
    and DeepSeek <think> blocks.
    """
    # 1. Remove <think> blocks if present
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    
    # 2. Find the first '{' and the last '}'
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return text[first_brace:last_brace+1]
    return text

async def generate_json(prompt: str, input_data: Any) -> Dict[str, Any]:
    """
    Combines the prompt and input_data into a single prompt string,
    then requests a JSON structure from the local Ollama instance.
    """
    
    # Serialize the input payload into JSON for context
    input_str = json.dumps(input_data, indent=2) if input_data else ""
    
    # Construct the full prompt
    # Strengthening the instruction for DeepSeek/Ollama
    full_prompt = (
        f"{prompt}\n\n"
        "=== INPUT DATA ===\n"
        f"{input_str}\n\n"
        "CRITICAL: You must return ONLY a JSON object. No preamble, no postamble, no markdown backticks, no reasoning blocks."
    )
    
    payload = {
        "model": MODEL_NAME,
        "prompt": full_prompt,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 8192 # Increased for large clinical fact lists
        }
    }
    
    async with httpx.AsyncClient(timeout=600.0) as client:
        response_text = ""
        try:
            response = await client.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            
            result = response.json()
            response_text = result.get("response", "").strip()
            
            # Extract and parse
            json_str = _extract_json(response_text)
            parsed_json = json.loads(json_str)
            return parsed_json
            
        except httpx.HTTPStatusError as e:
            error_msg = e.response.text
            logger.error(f"HTTP error from Ollama: {e}. Body: {error_msg}")
            raise Exception(f"Ollama returned HTTP error: {e}")
        except httpx.RequestError as e:
            logger.error(f"Error communicating with local Ollama: {type(e).__name__} - {e}")
            raise Exception(f"Failed to communicate with Ollama: {e}")
        except json.JSONDecodeError as e:
            # Provide more context on where it failed
            snippet = response_text[:200] + "..." if len(response_text) > 200 else response_text
            logger.error(f"Failed to parse JSON from Ollama. Snippet: {snippet}. Error: {e}")
            raise Exception(f"Ollama returned invalid JSON: {e}. Raw output length: {len(response_text)}")
async def generate_text(prompt: str, input_data: Any) -> str:
    """
    Combines the prompt and input_data into a single prompt string,
    then requests raw text from the local Ollama instance.
    """
    
    input_str = json.dumps(input_data, indent=2) if input_data else ""
    full_prompt = (
        f"{prompt}\n\n"
        "=== INPUT DATA ===\n"
        f"{input_str}\n\n"
    )
    
    payload = {
        "model": MODEL_NAME,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 8192
        }
    }
    
    async with httpx.AsyncClient(timeout=600.0) as client:
        try:
            response = await client.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from Ollama: {e}")
            raise Exception(f"Ollama returned HTTP error: {e}")
        except httpx.RequestError as e:
            logger.error(f"Error communicating with local Ollama: {e}")
            raise Exception(f"Failed to communicate with Ollama: {e}")
