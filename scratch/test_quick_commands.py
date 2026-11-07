import sys
sys.path.append('.')
from commands.router import CommandRouter
router = CommandRouter()
quick_commands = ['!note test note', '!remind test reminder', '!search python async', '!image cat', '!files list']
for cmd in quick_commands:
    print('Input:', cmd)
    try:
        res = router.route(cmd)
        print('Output:', res)
    except Exception as e:
        print('Error:', e)

