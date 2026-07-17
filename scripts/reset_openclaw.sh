#!/usr/bin/env bash
rm /home/riverwest/.openclaw/agents/main/sessions/*.jsonl
rm /home/riverwest/.openclaw/agents/main/sessions/*.json
openclaw gateway restart