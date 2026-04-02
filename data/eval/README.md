# Eval Data Format

`src/eval` expects each case file to be a JSON object with this structure:

```json
{
  "client_info": {
    "client_id": "case_id_or_number"
  },
  "global_plan": {},
  "sessions": [
    {
      "session_number": 1,
      "session_dialogue": [
        {"role": "user", "text": "..."},
        {"role": "assistant", "text": "..."}
      ]
    }
  ]
}
```

You can organize files either:

- directly under `data/eval/`
- or by modality folders such as `data/eval/bt/*.json`, `data/eval/cbt/*.json`, etc.
