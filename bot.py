import os
import discord
from discord import app_commands
from discord.ui import Modal, TextInput, Button, View, Select

intents = discord.Intents.default()
intents.message_content = True
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# In-memory storage for tasks
task_board_data = {
    "to_do": [],
    "in_progress": [],
    "completed": []
}

STATUS_LIST = ["to_do", "in_progress", "completed"]
STATUS_LABELS = {"to_do": "To Do", "in_progress": "In Progress", "completed": "Completed"}


class TaskModal(Modal, title="Create New Task"):
    task_title = TextInput(label="Task Title", placeholder="Enter task title...")
    task_description = TextInput(label="Task Description", placeholder="Enter task description...", style=discord.TextStyle.long)
    assignee = TextInput(label="Assignee (Optional)", placeholder="@username or name", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        title = self.task_title.value
        description = self.task_description.value
        assignee_val = self.assignee.value.strip() if self.assignee.value else ""
        task_board_data["to_do"].append({"title": title, "description": description, "assignee": assignee_val})
        await interaction.response.send_message(f"Task added to 'To Do': **{title}**", ephemeral=True)
        await update_task_board(interaction.channel)


class MoveToInProgressModal(Modal, title="Move to In Progress"):
    assignee = TextInput(label="Assign To", placeholder="@username or name — who's working on this?", required=False)
    notes = TextInput(label="Notes (Optional)", placeholder="Any notes about this task...", style=discord.TextStyle.long, required=False)

    def __init__(self, task_index: int, current_status: str) -> None:
        super().__init__()
        self.task_index = task_index
        self.current_status = current_status

    async def on_submit(self, interaction: discord.Interaction):
        if self.task_index >= len(task_board_data[self.current_status]):
            await interaction.response.send_message("Task no longer exists.", ephemeral=True)
            return
        task = task_board_data[self.current_status].pop(self.task_index)
        if self.assignee.value and self.assignee.value.strip():
            task["assignee"] = self.assignee.value.strip()
        if self.notes.value and self.notes.value.strip():
            task["description"] += f"\n\n**Notes:** {self.notes.value.strip()}"
        task_board_data["in_progress"].append(task)
        assignee_display = f" (assigned to {task['assignee']})" if task["assignee"] else ""
        await interaction.response.send_message(
            f"Moved to **In Progress**: {task['title']}{assignee_display}", ephemeral=True
        )
        await update_task_board(interaction.channel)


class MoveToCompletedModal(Modal, title="Mark as Completed"):
    assignee = TextInput(label="Completed By", placeholder="@username or name — who completed this?", required=False)
    notes = TextInput(label="Completion Notes (Optional)", placeholder="Summary of what was done...", style=discord.TextStyle.long, required=False)

    def __init__(self, task_index: int, current_status: str) -> None:
        super().__init__()
        self.task_index = task_index
        self.current_status = current_status

    async def on_submit(self, interaction: discord.Interaction):
        if self.task_index >= len(task_board_data[self.current_status]):
            await interaction.response.send_message("Task no longer exists.", ephemeral=True)
            return
        task = task_board_data[self.current_status].pop(self.task_index)
        if self.assignee.value and self.assignee.value.strip():
            task["assignee"] = self.assignee.value.strip()
        if self.notes.value and self.notes.value.strip():
            task["description"] += f"\n\n**Completed:** {self.notes.value.strip()}"
        task_board_data["completed"].append(task)
        assignee_display = f" (by {task['assignee']})" if task["assignee"] else ""
        await interaction.response.send_message(
            f"Marked as **Completed**: {task['title']}{assignee_display}", ephemeral=True
        )
        await update_task_board(interaction.channel)


class MoveToTodoModal(Modal, title="Move Back to To Do"):
    assignee = TextInput(label="Reassign To (Optional)", placeholder="@username or name", required=False)
    reason = TextInput(label="Reason (Optional)", placeholder="Why is this moving back?", style=discord.TextStyle.long, required=False)

    def __init__(self, task_index: int, current_status: str) -> None:
        super().__init__()
        self.task_index = task_index
        self.current_status = current_status

    async def on_submit(self, interaction: discord.Interaction):
        if self.task_index >= len(task_board_data[self.current_status]):
            await interaction.response.send_message("Task no longer exists.", ephemeral=True)
            return
        task = task_board_data[self.current_status].pop(self.task_index)
        if self.assignee.value and self.assignee.value.strip():
            task["assignee"] = self.assignee.value.strip()
        if self.reason.value and self.reason.value.strip():
            task["description"] += f"\n\n**Moved back:** {self.reason.value.strip()}"
        task_board_data["to_do"].append(task)
        await interaction.response.send_message(
            f"Moved back to **To Do**: {task['title']}", ephemeral=True
        )
        await update_task_board(interaction.channel)


class TaskView(View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(label="Add Task", style=discord.ButtonStyle.primary, custom_id='add_task_button')
    async def add_task_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TaskModal())

    @discord.ui.button(label="To Do", style=discord.ButtonStyle.secondary, custom_id='to_do_button')
    async def to_do_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await filter_tasks_by_status(interaction, "to_do")

    @discord.ui.button(label="In Progress", style=discord.ButtonStyle.secondary, custom_id='in_progress_button')
    async def in_progress_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await filter_tasks_by_status(interaction, "in_progress")

    @discord.ui.button(label="Completed", style=discord.ButtonStyle.success, custom_id='completed_button')
    async def completed_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await filter_tasks_by_status(interaction, "completed")


@bot.event
async def on_ready():
    bot.add_view(TaskView())
    await tree.sync()
    print(f'Logged in as {bot.user}')


@tree.command(name="taskboard", description="Create a task board")
async def task_board(interaction: discord.Interaction):
    view = TaskView()
    await interaction.response.send_message(view=view, embed=create_task_embed())


@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return
    custom_id = interaction.data.get('custom_id', '')

    # Handle "Start Task" buttons (move to in_progress)
    if custom_id.startswith('start_'):
        parts = custom_id.split('_', 2)  # start_{index}_{status}
        if len(parts) >= 3:
            try:
                idx = int(parts[1])
                status = parts[2]
                await interaction.response.send_modal(MoveToInProgressModal(idx, status))
            except (ValueError, IndexError):
                await interaction.response.send_message("Invalid task.", ephemeral=True)

    # Handle "Complete Task" buttons (move to completed)
    elif custom_id.startswith('complete_'):
        parts = custom_id.split('_', 2)  # complete_{index}_{status}
        if len(parts) >= 3:
            try:
                idx = int(parts[1])
                status = parts[2]
                await interaction.response.send_modal(MoveToCompletedModal(idx, status))
            except (ValueError, IndexError):
                await interaction.response.send_message("Invalid task.", ephemeral=True)

    # Handle "Back to To Do" buttons
    elif custom_id.startswith('backto_'):
        parts = custom_id.split('_', 2)  # backto_{index}_{status}
        if len(parts) >= 3:
            try:
                idx = int(parts[1])
                status = parts[2]
                await interaction.response.send_modal(MoveToTodoModal(idx, status))
            except (ValueError, IndexError):
                await interaction.response.send_message("Invalid task.", ephemeral=True)


async def update_task_board(channel):
    async for message in channel.history(limit=10):
        if message.author == bot.user and message.embeds and message.embeds[0].title == "Task Board":
            await message.edit(embed=create_task_embed(), view=TaskView())
            break


async def filter_tasks_by_status(interaction: discord.Interaction, status: str):
    filtered_tasks = task_board_data[status]
    status_colors = {"to_do": discord.Color.red(), "in_progress": discord.Color.orange(), "completed": discord.Color.green()}
    embed = discord.Embed(
        title=f"Tasks \u2014 {STATUS_LABELS[status]}",
        color=status_colors.get(status, discord.Color.blue())
    )

    if filtered_tasks:
        view = View(timeout=300)
        for idx, task in enumerate(filtered_tasks):
            assignee_str = f" (Assigned to {task['assignee']})" if task['assignee'] else ""
            embed.add_field(
                name=f"Task {idx + 1}: {task['title']}{assignee_str}",
                value=task['description'][:1024],
                inline=False
            )
            # Add contextual move buttons based on current status
            if status == "to_do":
                view.add_item(Button(
                    label=f"Start #{idx + 1}",
                    style=discord.ButtonStyle.primary,
                    custom_id=f'start_{idx}_{status}',
                    emoji="\u25b6"
                ))
                view.add_item(Button(
                    label=f"Complete #{idx + 1}",
                    style=discord.ButtonStyle.success,
                    custom_id=f'complete_{idx}_{status}',
                    emoji="\u2705"
                ))
            elif status == "in_progress":
                view.add_item(Button(
                    label=f"Complete #{idx + 1}",
                    style=discord.ButtonStyle.success,
                    custom_id=f'complete_{idx}_{status}',
                    emoji="\u2705"
                ))
                view.add_item(Button(
                    label=f"Back #{idx + 1}",
                    style=discord.ButtonStyle.secondary,
                    custom_id=f'backto_{idx}_{status}',
                    emoji="\u25c0"
                ))
            elif status == "completed":
                view.add_item(Button(
                    label=f"Reopen #{idx + 1}",
                    style=discord.ButtonStyle.secondary,
                    custom_id=f'backto_{idx}_{status}',
                    emoji="\u21a9"
                ))
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    else:
        embed.description = "No tasks found."
        await interaction.response.send_message(embed=embed, ephemeral=True)


def create_task_embed():
    embed = discord.Embed(title="Task Board", description="Manage your tasks here!", color=discord.Color.green())
    for status in STATUS_LIST:
        task_list = "\n".join([
            f"\u2022 {task['title']} ({task['assignee']})" if task['assignee']
            else f"\u2022 {task['title']}"
            for task in task_board_data[status]
        ]) if task_board_data[status] else "No tasks"
        embed.add_field(name=STATUS_LABELS[status].upper(), value=task_list, inline=True)
    return embed


bot.run(os.environ['DISCORD_BOT_TOKEN'])
