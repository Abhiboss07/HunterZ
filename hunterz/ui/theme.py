"""Custom design system, colors, and CSS for HunterZ CRM Terminal Dashboard."""

TUI_CSS = """
Screen {
    background: #070A10;
    color: #F8FAFC;
}

Header {
    background: #0E1626;
    color: #00F2FE;
    text-style: bold;
    height: 3;
    dock: top;
    content-align: center middle;
    border-bottom: heavy #1E293B;
}

Footer {
    background: #0E1626;
    color: #94A3B8;
    height: 1;
    dock: bottom;
}

Tabs {
    background: #0B1120;
    border-bottom: solid #1E293B;
}

Tab {
    color: #94A3B8;
    padding: 0 3;
}

Tab:hover {
    color: #F8FAFC;
    background: #1E293B;
}

Tab.-active {
    color: #00F2FE;
    background: #111827;
    text-style: bold;
}

Underline {
    color: #00F2FE;
}

#stats-panel {
    layout: grid;
    grid-size: 5;
    grid-columns: 1fr 1fr 1fr 1fr 1fr;
    height: 5;
    background: #0B1120;
    margin: 1 1 0 1;
    border: round #1E293B;
    padding: 0 1;
}

.stat-box {
    content-align: center middle;
    border-right: solid #1E293B;
}

.stat-box:last-child {
    border-right: none;
}

.stat-label {
    color: #94A3B8;
    text-align: center;
}

.stat-val-cyan {
    color: #00F2FE;
    text-align: center;
    text-style: bold;
}

.stat-val-green {
    color: #10B981;
    text-align: center;
    text-style: bold;
}

.stat-val-amber {
    color: #F59E0B;
    text-align: center;
    text-style: bold;
}

.stat-val-purple {
    color: #A855F7;
    text-align: center;
    text-style: bold;
}

/* CRM Split Workspace */
#feed-split {
    layout: horizontal;
    height: 1fr;
    margin: 0 1 1 1;
}

#feed-table-container {
    width: 58%;
    height: 100%;
}

#feed-dossier-container {
    width: 42%;
    height: 100%;
    background: #0B1120;
    border: round #1E293B;
    margin-left: 1;
    padding: 1;
    overflow-y: scroll;
}

/* Filter Quick Bar */
#quick-filters {
    height: 3;
    margin: 0 0 1 0;
    background: #0B1120;
    border: solid #1E293B;
    padding: 0 1;
}

#quick-filters Button {
    margin: 0 1;
    height: 1;
    min-width: 10;
    padding: 0 1;
}

DataTable {
    background: #0B1120;
    color: #F8FAFC;
    border: round #1E293B;
    height: 1fr;
}

DataTable > .datatable--header {
    background: #111827;
    color: #00F2FE;
    text-style: bold;
}

DataTable > .datatable--cursor {
    background: #1E293B;
    color: #FFFFFF;
    text-style: bold;
}

#action-buttons {
    margin-top: 1;
    layout: horizontal;
}

#action-buttons Button {
    margin-right: 1;
}

/* CRM Profile Editor Inputs */
.profile-input-row {
    layout: horizontal;
    height: 3;
    margin-bottom: 1;
}

.profile-input-label {
    width: 20;
    content-align: left middle;
    color: #00F2FE;
    text-style: bold;
}

.profile-input-field {
    width: 1fr;
}

Button {
    background: #1E293B;
    color: #F8FAFC;
    border: none;
}

Button:hover {
    background: #00F2FE;
    color: #070A10;
    text-style: bold;
}

Button.-success {
    background: #059669;
    color: #FFFFFF;
}

Button.-success:hover {
    background: #10B981;
}
"""
