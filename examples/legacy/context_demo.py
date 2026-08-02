#!/usr/bin/env python3
"""Legacy minimal DeepSeek conversation loop."""
from openai import OpenAI
import os
client = OpenAI(api_key=os.environ.get("DS_API"), base_url="https://api.deepseek.com")
messages = [{"role": "system", "content": "你是一名顶级AI助手，回答简洁专业。"}]

while True:
    try:
        user_input = input("\nUser: ").strip()
    except (EOFError, KeyboardInterrupt):
        break
    if not user_input or user_input.lower() in ("exit", "quit", "q"):
        break

    messages.append({"role": "user", "content": user_input})

    while len(messages) > 11:
        messages.pop(1)

    response = client.chat.completions.create(model="deepseek-chat", messages=messages)
    reply = response.choices[0].message.content or ""
    print(f"\nAssistant: {reply}")

    # encode/decode 忽略异常字符，防止 UnicodeEncodeError 报错
    clean_reply = reply.encode("utf-8", "ignore").decode("utf-8")
    messages.append({"role": "assistant", "content": clean_reply})
