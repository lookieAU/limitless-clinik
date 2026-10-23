DATE = {"type": "string", "description": "YYYY-MM-DD in the clinic's timezone"}
CLOCK = {"type": "string", "description": "HH:MM 24h in the clinic's timezone"}
REF = {"type": "string", "description": "clinic booking reference such as CA-1003; omit to use the booking already in focus"}

TOOL_SPECS = [
    {
        "name": "current_time",
        "description": "Get today's date, weekday and the current time in the clinic's and the customer's timezones.",
        "input_schema": {"type": "object", "properties": {"clinic_id": {"type": "string"}}},
    },
    {
        "name": "check_availability",
        "description": "List free slots at a clinic. Always call this before offering or booking a slot.",
        "input_schema": {
            "type": "object",
            "properties": {
                "clinic_id": {"type": "string"},
                "doctor_id": {"type": "string"},
                "date_from": DATE,
                "date_to": DATE,
                "time_from": CLOCK,
                "time_to": CLOCK,
            },
            "required": ["date_from"],
        },
    },
    {
        "name": "propose_slot",
        "description": (
            "Offer one slot to the customer without booking it. Use when the customer gave a window or the exact slot "
            "they asked for is unavailable. The system renders the offer and waits for their yes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"slot_id": {"type": "string"}, "action": {"type": "string", "enum": ["book", "reschedule"]}},
            "required": ["slot_id"],
        },
    },
    {
        "name": "book",
        "description": "Book a slot the customer explicitly chose (exact day and time) or accepted from an offer.",
        "input_schema": {"type": "object", "properties": {"slot_id": {"type": "string"}}, "required": ["slot_id"]},
    },
    {
        "name": "reschedule",
        "description": "Move the customer's existing booking to a slot they explicitly chose or accepted.",
        "input_schema": {
            "type": "object",
            "properties": {"slot_id": {"type": "string"}, "booking_ref": REF},
            "required": ["slot_id"],
        },
    },
    {
        "name": "cancel",
        "description": "Cancel the customer's booking. Only when they asked to cancel in this message.",
        "input_schema": {"type": "object", "properties": {"booking_ref": REF}},
    },
    {
        "name": "get_booking",
        "description": "Re-check a booking's current status at the clinic. Call before saying anything about status.",
        "input_schema": {"type": "object", "properties": {"booking_ref": REF}},
    },
    {
        "name": "recall",
        "description": "Search what the customer said in earlier sessions. Results are claims, not facts.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}, "k": {"type": "integer"}},
            "required": ["query"],
        },
    },
]
