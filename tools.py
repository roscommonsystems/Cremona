TOOLS = [
    {
        "type": "function",
        "name": "get_time",
        "description": "Get the current time and date.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "type": "function",
        "name": "create_memory",
        "description": (
            "Save a piece of information to persistent memory. "
            "Use this when the user expresses a preference or asks you to remember something "
            "(e.g. 'remember I prefer concise answers', 'I work in finance'). "
            "Memories are loaded on startup and injected into your system prompt."
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "memory_topic": {
                    "type": "string",
                    "description": "Short category label for the memory (e.g. 'communication style')."
                },
                "memory_content": {
                    "type": "string",
                    "description": "The actual information to remember (e.g. 'user prefers concise responses')."
                }
            },
            "required": ["memory_topic", "memory_content"],
            "additionalProperties": False
        }
    },
    {
        "type": "function",
        "name": "change_voice",
        "description": "Change the agent's voice. Call this when the user asks to change, switch, or use a different voice.",
        "parameters": {
            "type": "object",
            "properties": {
                "voice": {
                    "type": "string",
                    "description": "The voice name to switch to.",
                    "enum": ["alexei","alexis","andy","anna","antoine","audrey","brian","claire","dawn","diana","dylan","gautam","grace","jennie","josh","kai","kenji","kevin","leo","lily","luke","marco","max","melissa","michael","nathan","nova","pete","santiago","sofia","summer","will","yuki","zoe"]
                }
            },
            "required": ["voice"]
        }
    },
]
# alexei = russian male
# alexis = american girl
# andy = stoned college kid male
# anna = pleasant american female hippy
# antoine = french young male
# audrey = mature neutral accent, female, dramatic
# brian = young american boy
# claire = girl american, female, upbeat and friendly, positive
# dawn = female, soft voice, american
# diana = refined female, mature, elegant
# dylan = straight forward, male, middle age american
# gautam = indian, male, slow paced, microsoft tech support
# grace = woman, mysterious, dramatic, mature
# jennie = daintly, delicate, female, young
# josh = man, american, middle age, neutral accent
# kai = stoned, california, ditzy, female, 
# kenji =  male, confident, japanese accent, 
# kevin = male, clear, casual, neutral, conversational
# leo = male, deep, italian accent, Portuguese accent
# lily = female, cultured, academic 
