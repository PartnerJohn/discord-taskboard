import os
import discord
from discord.ext import commands
from discord.ui import Modal, InputText, Button, View

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# In-memory storage for tasks
task_board_data = {
    "to_do": [],
    "in_progress": [],
    "completed": []
}

STATUS_LIST = ["to_do", "in_progress", "completed"]


class TaskModal(Modal):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.add_item(InputText(label="Task Title", placeholder="Enter task title..."))
        self.add_item(InputText(label="Task Description", placeholder="Enter task description...", style=discord.InputTextStyle.long))
        self.add_item(InputText(label="Assignee (Optional)", placeholder="Username of the assignee", required=False))

    async def callback(self, interaction: discord.Interaction):
        title = self.children[0].value
        description = self.children[1].value
        assignee = self.children[2].value.strip() if self.children[2].value else ""
        task_board_data["to_do"].append({"title": title, "description": description, "assignee": assignee})
        await interaction.response.send_message(f"Task added to 'To Do': **{title}**", ephemeral=True)
        await update_task_board(interaction.channel)


class TaskTransitionModal(Modal):
    def __init__(self, task_index: int, current_status: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.task_index = task_index
        self.current_status = current_status
        statuses = [s for s in STATUS_LIST if s != current_status]
        self.add_item(InputText(label="New Status", placeholder=f"Choose from: {', '.join(statuses)}"))

    async def callback(self, interaction: discord.Interaction):
        new_status = self.children[0].value.strip().lower()
        if new_status in STATUS_LIST and new_status != self.current_status:
            if self.task_index < len(task_board_data[self.current_status]):
                task = task_board_data[self.current_status].pop(self.task_index)
                task_board_data[new_status].append(task)
                await interaction.response.send_message(
                    f"Task moved to **{new_status}**: {task['title']}", ephemeral=True
                )
                await update_task_board(interaction.channel)
            else:
                await interaction.response.send_message("Task no longer exists at that index.", ephemeral=True)
        else:
            valid = [s for s in STATUS_LIST if s != self.current_status]
            await interaction.response.send_message(
                f"Invalid status. Choose from: {', '.join(valid)}", ephemeral=True
            )


class TaskView(View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Add Task", style=discord.ButtonStyle.primary, custom_id='add_task_button')
    async def add_task_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        modal = TaskModal(title="Create New Task")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="To Do", style=discord.ButtonStyle.secondary, custom_id='to_do_button')
    async def to_do_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await filter_tasks_by_status(interaction, "to_do")

    @discord.ui.button(label="In Progress", style=discord.ButtonStyle.secondary, custom_id='in_progress_button')
    async def in_progress_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await filter_tasks_by_status(interaction, "in_progress")

    @discord.ui.button(label="Completed", style=discord.ButtonStyle.success, custom_id='completed_button')
    async def completed_button(self, button: discord.ui.Button, interaction: discord.Interaction):
        await filter_tasks_by_status(interaction, "completed")


class MoveTaskView(View):
    def __init__(self, task_index: int, current_status: str) -> None:
        super().__init__(timeout=120)
        self.add_item(Button(
            label="Move Task",
            style=discord.ButtonStyle.grey,
            custom_id=f'task_{task_index}_{current_status}'
        ))


@bot.event
async def on_ready():
    bot.add_view(TaskView())  # Re-register persistent view
    print(f'Logged in as {bot.user}')


@bot.slash_command(name="taskboard", description="Create a task board")
async def task_board(ctx: discord.ApplicationContext):
    view = TaskView()
    await ctx.respond(view=view, embed=create_task_embed())


@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return
    custom_id = interaction.data.get('custom_id', '')
    if custom_id.startswith('task_'):
        parts = custom_id.split('_', 2)  # task_{index}_{status}
        if len(parts) >= 3:
            try:
                task_index = int(parts[1])
                current_status = parts[2]
                if current_status in STATUS_LIST:
                    modal = TaskTransitionModal(task_index, current_status, title=f"Move Task {task_index + 1}")
                    await interaction.response.send_modal(modal)
            except (ValueError, IndexError):
                await interaction.response.send_message("Invalid task reference.", ephemeral=True)


async def update_task_board(channel: discord.TextChannel):
    async for message in channel.history(limit=10):
        if message.author == bot.user and message.embeds and message.embeds[0].title == "Task Board":
            await message.edit(embed=create_task_embed(), view=TaskView())
            break


async def filter_tasks_by_status(interaction: discord.Interaction, status: str):
    filtered_tasks = task_board_data[status]
    status_colors = {"to_do": discord.Color.red(), "in_progress": discord.Color.orange(), "completed": discord.Color.green()}
    embed = discord.Embed(title=f"Tasks — {status.replace('_', ' ').upper()}", color=status_colors.get(status, discord.Color.blue()))

    if filtered_tasks:
        view = View(timeout=120)
        for idx, task in enumerate(filtered_tasks):
            assignee_str = f" (Assigned to @{task['assignee']})" if task['assignee'] else ""
            embed.add_field(
                name=f"Task {idx + 1}: {task['title']}{assignee_str}",
                value=task['description'],
                inline=False
            )
            view.add_item(Button(
                label=f"Move Task {idx + 1}",
                style=discord.ButtonStyle.grey,
                custom_id=f'task_{idx}_{status}'
            ))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    else:
        embed.description = "No tasks found."
        await interaction.response.send_message(embed=embed, ephemeral=True)


def create_task_embed():
    embed = discord.Embed(title="Task Board", description="Manage your tasks here!", color=discord.Color.green())
    for status in STATUS_LIST:
        task_list = "\n".join([
            f"• {task['title']} (Assigned to @{task['assignee']})" if task['assignee']
            else f"• {task['title']}"
            for task in task_board_data[status]
        ]) if task_board_data[status] else "No tasks"
        embed.add_field(name=status.replace('_', ' ').upper(), value=task_list, inline=True)
    return embed


bot.run(os.environ['DISCORD_BOT_TOKEN'])
