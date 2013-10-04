import sublime

from . import SublimeHelper as SH
from . import OsShell


class ShellCommandCommand(SH.TextCommand):

    def __init__(self, plugin, default_prompt=None, **kwargs):

        SH.TextCommand.__init__(self, plugin, **kwargs)
        if default_prompt is None:
            self.default_prompt = 'Shell Command'
        else:
            self.default_prompt = default_prompt
        self.data_key = 'ShellCommand'

    def run(self, edit, command='', command_prefix=None, prompt=None, region=False, arg_required=False, panel=False, title=None, syntax=None, refresh=False):

        # If regions should be used then work them out, and append
        # them to the command:
        #
        if region is True:
            arg = self.get_region().strip()

            if arg == '':
                if arg_required is True:
                    SH.error_message('This command requires a parameter.')
                    return
            else:
                command = command + ' ' + arg

        # Setup a closure to run the command:
        #
        def _C(command):

            if command_prefix is not None:
                command = command_prefix + ' ' + command

            self.run_shell_command(command, panel=panel, title=title, syntax=syntax, refresh=refresh)

        # If no command is specified then we prompt for one, otherwise
        # we can just execute the command:
        #
        if command.strip() == '':
            if prompt is None:
                prompt = self.default_prompt
            self.view.window().show_input_panel(prompt, '', _C, None, None)
        else:
            _C(command)

    def run_shell_command(self, command, panel=False, title=None, syntax=None, refresh=False):

        view = self.view
        window = view.window()

        if command.strip() == '':
            SH.error_message('No command provided.')
            return

        working_dir = self.get_working_dir()

        # Run the command and write any output to the buffer:
        #
        def _C(output):

            output = output.strip()
            if output == '':
                output = 'Shell command succeeded with no output'

            # If we didn't get any output then don't do anything:
            #
            if output != '':
                # If a panel has been requested then create one and show it,
                # otherwise create a new buffer, and set its caption:
                #
                if panel is True:
                    console = window.get_output_panel('ShellCommand')
                    window.run_command('show_panel', {'panel': 'output.ShellCommand'})
                else:
                    console = window.new_file()
                    caption = title if title else '*Shell Command Output*'
                    console.set_name(caption)

                # Indicate that this buffer is a scratch buffer:
                #
                console.set_scratch(True)

                # Set the syntax for the output:
                #
                if syntax is not None:
                    resources = sublime.find_resources(syntax + '.tmLanguage')
                    console.set_syntax_file(resources[0])

                # Insert the output into the buffer:
                #
                console.set_read_only(False)
                console.run_command('insert_text', {'pos': 0, 'msg': output})
                console.set_read_only(True)

                # Set a flag on the view that we can use in key bindings:
                #
                settings = console.settings()
                settings.set(self.data_key, True)

                # Also, save the command and working directory for later,
                # since we may need to refresh the panel/window:
                #
                data = {
                    'command': command,
                    'working_dir': working_dir
                }
                settings.set(self.data_key + '_data', data)

            if refresh is True:
                view.run_command('shell_command_refresh')

        OsShell.process(command, _C, working_dir=working_dir)


# Refreshing a shell command simply involves re-running the original command:
#
class ShellCommandRefreshCommand(ShellCommandCommand):

    def run(self, edit, callback=None):

        view = self.view

        settings = view.settings()
        if settings.has(self.data_key):
            data = settings.get(self.data_key + '_data', None)
            if data is not None:

                # Create a local function that will re-write the buffer contents:
                #
                def _C(output, **kwargs):

                    console = view

                    console.set_read_only(False)
                    region = sublime.Region(0, view.size())
                    console.run_command('erase_text', {'a': region.a, 'b': region.b})
                    console.run_command('insert_text', {'pos': 0, 'msg': output})
                    console.set_read_only(True)

                    if callback is not None:
                        callback()

                OsShell.process(data['command'], _C, working_dir=data['working_dir'])