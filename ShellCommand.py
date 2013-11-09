import re
import os
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

    def run(self, edit, command=None, prompt=None, region=None, arg_required=None, out_to='view', title=None, syntax=None, refresh=None, output_filter=None):
        ''' :param out_to: which to output the result. 'view', 'panel' or 'quickpanel'. Default is 'view'.
        '''
        if region is None:
            region is False
        if arg_required is None:
            arg_required = False
        if refresh is None:
            refresh = False
        arg = None

        # If regions should be used then work them out, and append
        # them to the command:
        #
        if region is True:
            arg = self.get_region().strip()

            if arg == '':
                if arg_required is True:
                    sublime.message_dialog('This command requires a parameter.')
                    return

        # If no command is specified then we prompt for one, otherwise
        # we can just execute the command:
        #
        to_asks, template = self.parse_command(command)

        def _on_input_end(arglist):
            print(to_asks, arglist, template)
            if len(to_asks) != len(arglist):
                return
            argstr = template.format('', *arglist)
            self.run_shell_command(argstr, out_to=out_to, title=title, syntax=syntax,
                                   refresh=refresh, output_filter=output_filter)
        if to_asks:
            self.ask_to_user(to_asks, _on_input_end)

    def ask_to_user(self, asks, callback):
        asks = asks[:]
        arglist = []
        def _on_done(arg):
            arglist.append(arg)
            if asks:
                _run()
            else:
                callback(arglist)
        def _on_cancel():
            callback([])
        def _run():
            self.view.window().show_input_panel(asks.pop(0), '', _on_done, None, _on_cancel)
        _run()

    def parse_command(self, command):
        ''' Inspired by Sublime's snippet syntax; "${1:prompt}" is a variable.'''
        if not command:
            return [self.default_prompt], '{0}'
        parsed = re.split(r'\${(.*?)}', command)
        # if not variables, return command itself
        if len(parsed) == 1:
            return [], command
        template_parts = []
        asks = {}
        for idx, item in enumerate(parsed, start=1):
            # variable
            if idx % 2 == 0:
                v = self.judge_special_variable(item)
                if v:
                    template_parts.append(v)
                    continue
                chs = item.split(':')
                num = int(chs[0])
                prompt = chs[1] if len(chs) > 1 else self.default_prompt
                asks[num] = prompt
                template_parts.append('{%d}' % num)
            else:
                template_parts.append(item)
        return [y for x, y in sorted(asks.items(), key=lambda x: x[0])], ''.join(template_parts)

    def judge_special_variable(self, item):
        if item == 'project_folders':
            return ' '.join(self.view.window().folders() or [])

    def run_shell_command(self, command=None, out_to='view', title=None, syntax=None, refresh=False, output_filter=None):

        view = self.view
        window = view.window()

        if command is None:
            sublime.message_dialog('No command provided.')
            return

        working_dir = self.get_working_dir()

        # Run the command and write any output to the buffer:
        #
        def _C(output):

            output = output.strip()
            if output == '':
                settings = sublime.load_settings('ShellCommand.sublime-settings')
                show_message = settings.get('show_success_but_no_output_message')
                if show_message:
                    output = settings.get('success_but_no_output_message')

            # If we didn't get any output then don't do anything:
            #
            if output != '':
                # create outputs. To view, panel, or quick panel.
                if out_to == 'view':
                    console = window.new_file()
                    caption = title if title else '*Shell Command Output*'
                    console.set_name(caption)
                elif out_to == 'panel':
                    console = window.get_output_panel('ShellCommand')
                    window.run_command('show_panel', {'panel': 'output.ShellCommand'})
                elif out_to == 'quickpanel':
                    self.out_to_quick_panel(output, output_filter)
                    return

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
                console.run_command('sublime_helper_insert_text', {'pos': 0, 'msg': output})
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

    def out_to_quick_panel(self, output, output_filter):
        view = self.view
        window = view.window()
        items = []

        def _on_done(index):
            if index == -1:
                window.focus_view(view)
                return
            path = items[index]
            if not os.path.exists(path):
                window.focus_view(view)
                return
            open_view = window.open_file(path)
            if open_view:
                window.focus_view(open_view)

        if isinstance(output_filter, (list, tuple)) and len(output_filter) == 2:
            pattern, mapping = output_filter
            for mo in re.finditer(pattern, output):
                items.append(mo.expand(mapping))
            self.view.window().show_quick_panel(items, _on_done, 0, 0, None)


class ShellCommandOnRegionCommand(ShellCommandCommand):

    def run(self, edit, command=None, prompt=None, arg_required=None, panel=None, title=None, syntax=None, refresh=None):

        ShellCommandCommand.run(self, edit, command=command, prompt=prompt, region=True, arg_required=True, panel=panel, title=title, syntax=syntax, refresh=refresh)


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
                    console.run_command('sublime_helper_erase_text', {'a': region.a, 'b': region.b})
                    console.run_command('sublime_helper_insert_text', {'pos': 0, 'msg': output})
                    console.set_read_only(True)

                    if callback is not None:
                        callback()

                OsShell.process(data['command'], _C, working_dir=data['working_dir'])
