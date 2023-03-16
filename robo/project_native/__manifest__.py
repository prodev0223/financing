# -*- coding: utf-8 -*-
{
    "name": """Gantt Native view for Projects""",
    "summary": """Added support Gantt""",
    "category": "Project",
    "images": ['static/description/icon.png'],
    "version": "10.18.2.2.0",
    "description": """
    Update 1: Add Milestone icon on Gantt bar.
    Update 2: Add Progress Bar and Task Nanme on Gantt.
    Update 3: Add New Scale.
    Update 4: link between tasks with arrows.
    Update 5: Gantt for Sub-task View.
    Update 6: Done on Gantt, Ghosts bar on Gantt. Manufacture support.
    fix: Sorted if more that 10.
    Update 7: Autosheduling support and constraint for tasks.
    fix: Can't change project if predecessor or parent_id for sub-task exist
    fix: predessort - task_id if null.
    Update 8: Autosheduling support with Predecessor Lag and Summary Task.
    Update 9: Custom Color for Task
    fix: default = Custom Color for Task  
    Fix: End date in task - default.
    Update 11: Start Date for Project. 
    Update 12: Today and Scale button in Odoo Native place.
        Frozen Header and horizontal - vertical scroll. 
    Update 13: Forward and Backward Scheduling.
    Update 14: In project you can set' humanized duration scale for tasks.
    Fix: datalist check
    Update 15: Calendar
    
""",
    "author": "Viktor Vorobjov",
    "license": "OPL-1",
    "website": "https://straga.github.io",
    "support": "vostraga@gmail.com",

    "depends": [
        "project",
        "hr_timesheet",
        "web_gantt_native",
        "web_widget_time_delta",
        "web_widget_colorpicker",
        "robo_depend",
        "robo_basic",
        "robo",
    ],
    "external_dependencies": {"python": [], "bin": []},
    "data": [
        'views/project_task_view.xml',
        'views/project_task_detail_plan_view.xml',
        'views/project_calendar_access_view.xml',
        'views/resource_view.xml',
        'security/ir.model.access.csv',
    ],
    "qweb": [],
    "demo": [],

    "post_load": None,
    "pre_init_hook": None,
    "post_init_hook": None,
    "installable": True,
    "auto_install": False,
    "application": False,
}