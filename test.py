from openai import OpenAI

client = OpenAI(
    api_key="sk-trollllm-d5a60b5266b264a670a8776c39a1a69c8d89c506c0f3a30868f2fca33f875006",
    base_url="https://chat.trollllm.xyz/v1",
)

response = client.chat.completions.create(
    model="gemini-3-flash", messages=[{"role": "user", "content": "Hello!"}]
)

print(response.choices[0].message.content)
