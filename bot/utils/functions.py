def is_yes(content: str):
    if content.lower() in ['yes', 'y']:
        return True
    return False


async def send_dm(member, *args, **kwargs):
    try:
        msg = await member.send(*args, **kwargs)
        return msg
    except:
        return None
