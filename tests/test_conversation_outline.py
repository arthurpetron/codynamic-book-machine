from scripts.book.conversation_outline import ConversationOutlineService


def test_outline_conversation_reply_does_not_repeat_answered_reader_question(tmp_path):
    service = ConversationOutlineService(tmp_path)
    messages = [
        {
            "role": "assistant",
            "content": "What book are we making, who is it for, and what should be true for the reader by the end?",
        },
        {
            "role": "user",
            "content": (
                "I want to make a book about the rules of pool that includes APA, BCA, English, "
                "Snooker, Poker, and other games."
            ),
        },
        {
            "role": "assistant",
            "content": "Who is the reader, and what do they already understand before opening the book?",
        },
        {
            "role": "user",
            "content": "The reader wants to play pool games.",
        },
    ]

    reply = service.reply(messages, use_llm="never")

    assert "who is the reader" not in reply.lower()
    assert "reader" not in reply.lower() or "press create outline" in reply.lower()
    assert reply
