try:
    from llm_client import GeminiClient
    print("Import successful")
    client = GeminiClient()
    print("Instantiation successful")
except Exception as e:
    print(f"Error: {e}")
