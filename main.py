"""
main.py - Main Application Shell & Entry Point for FD Manager
Fixed Deposit Portfolio Management System
Integrates Tkinter/ttk GUI, SQLite database, PBKDF2 authentication,
role-based navigation (Admin vs Customer), and data visualization.
"""

from datetime import date
import os
import sys
import tempfile
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

# Ensure matplotlib uses a writable temp configuration folder
os.environ.setdefault("MPLCONFIGDIR", tempfile.gettempdir())

from auth import session
from database import init_db, sync_fd_statuses
from seed_data import seed_database
from ui.admin_dashboard import AdminDashboardView
from ui.calculator_view import CalculatorView
from ui.customer_dashboard import CustomerDashboardView
from ui.customer_management import CustomerManagementView
from ui.fd_management import FDManagementView
from ui.login import LoginFrame
from ui.reports import ReportsView
from ui.styles import COLORS, FONTS, apply_theme


class FDManagerApp(tk.Tk):
    """Primary Window and Shell Controller for FD Manager."""

    def __init__(self):
        super().__init__()

        # Window Metadata
        self.title("FD Manager — Fixed Deposit Portfolio Management System")
        self.geometry("1280x820")
        self.minsize(1024, 680)

        # Center on screen
        self._center_window(1280, 820)

        # Apply Modern TTK Styles
        self.style = apply_theme(self)

        # Initialize and Seed Database
        init_db()
        seed_database()
        sync_fd_statuses()

        # View Containers
        self.current_shell: Optional[tk.Widget] = None
        self.login_frame: Optional[LoginFrame] = None

        # Start at Login Screen
        self.show_login()

    def _center_window(self, width: int, height: int):
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2 - 20)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def show_login(self):
        """Display the authentication screen."""
        if self.current_shell:
            self.current_shell.destroy()
            self.current_shell = None

        self.login_frame = LoginFrame(self, on_login_success=self._on_login_success)
        self.login_frame.pack(fill="both", expand=True)

    def _on_login_success(self, user_dict: dict):
        """Route to appropriate shell based on role."""
        if self.login_frame:
            self.login_frame.destroy()
            self.login_frame = None

        if session.is_admin():
            self._build_admin_shell()
        else:
            self._build_customer_shell()

    def _handle_logout(self):
        """End session and return to login."""
        confirm = messagebox.askyesno("Confirm Sign Out", "Are you sure you want to sign out of the system?")
        if confirm:
            session.logout()
            self.show_login()

    # =========================================================================
    # Admin Application Shell
    # =========================================================================

    def _build_admin_shell(self):
        """Build administrator workbench with dark sidebar and multi-view content."""
        self.current_shell = ttk.Frame(self, style="TFrame")
        self.current_shell.pack(fill="both", expand=True)

        # 1. Left Sidebar
        sidebar = tk.Frame(self.current_shell, bg=COLORS["bg_sidebar"], width=240)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Sidebar Header Branding
        brand_frame = tk.Frame(sidebar, bg=COLORS["bg_sidebar"], padx=18, pady=20)
        brand_frame.pack(fill="x")

        logo_title = tk.Label(
            brand_frame,
            text="🏛  FD Manager",
            font=FONTS["app_title"],
            fg="#FFFFFF",
            bg=COLORS["bg_sidebar"],
            anchor="w",
        )
        logo_title.pack(fill="x")

        logo_sub = tk.Label(
            brand_frame,
            text="Portfolio Management System",
            font=FONTS["app_subtitle"],
            fg=COLORS["text_sidebar_muted"],
            bg=COLORS["bg_sidebar"],
            anchor="w",
        )
        logo_sub.pack(fill="x", pady=(2, 0))

        # Divider
        tk.Frame(sidebar, bg="#334155", height=1).pack(fill="x", pady=(0, 12))

        # User Badge
        user_card = tk.Frame(sidebar, bg="#1E293B", padx=14, pady=10)
        user_card.pack(fill="x", padx=14, pady=(0, 16))

        tk.Label(
            user_card,
            text=f"👑  {session.full_name}",
            font=FONTS["body_bold"],
            fg="#FFFFFF",
            bg="#1E293B",
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            user_card,
            text="System Administrator",
            font=FONTS["body_small"],
            fg="#38BDF8",
            bg="#1E293B",
            anchor="w",
        ).pack(fill="x")

        # Navigation Buttons Container
        self.nav_container = tk.Frame(sidebar, bg=COLORS["bg_sidebar"])
        self.nav_container.pack(fill="both", expand=True)

        self.nav_buttons = {}
        nav_items = [
            ("dashboard", "📊  Dashboard", lambda: self._show_admin_view("dashboard")),
            ("customers", "👥  Customers", lambda: self._show_admin_view("customers")),
            ("fds", "💰  Fixed Deposits", lambda: self._show_admin_view("fds")),
            ("reports", "📈  Reports & Exports", lambda: self._show_admin_view("reports")),
            ("calculator", "🧮  Maturity Calculator", lambda: self._show_admin_view("calculator")),
        ]

        for key, text, cmd in nav_items:
            btn = tk.Button(
                self.nav_container,
                text=text,
                font=FONTS["nav_item"],
                fg=COLORS["text_sidebar_muted"],
                bg=COLORS["bg_sidebar"],
                activebackground=COLORS["bg_sidebar_hover"],
                activeforeground="#FFFFFF",
                anchor="w",
                padx=18,
                pady=10,
                relief="flat",
                cursor="hand2",
                command=cmd,
            )
            btn.pack(fill="x", pady=1)
            self.nav_buttons[key] = btn

        # Logout Button at Bottom of Sidebar
        logout_btn = tk.Button(
            sidebar,
            text="🚪  Sign Out",
            font=FONTS["nav_item"],
            fg="#EF4444",
            bg=COLORS["bg_sidebar"],
            activebackground="#450A0A",
            activeforeground="#FCA5A5",
            anchor="w",
            padx=18,
            pady=12,
            relief="flat",
            cursor="hand2",
            command=self._handle_logout,
        )
        logout_btn.pack(side="bottom", fill="x", pady=12)

        # 2. Main Content Area
        self.admin_content_area = ttk.Frame(self.current_shell, style="TFrame")
        self.admin_content_area.pack(side="left", fill="both", expand=True)

        # Load initial view
        self._show_admin_view("dashboard")

    def _show_admin_view(self, view_name: str, **kwargs):
        """Switch views in the admin content panel."""
        for child in self.admin_content_area.winfo_children():
            child.destroy()

        # Update sidebar active highlighting
        for key, btn in self.nav_buttons.items():
            if key == view_name:
                btn.config(bg="#1E293B", fg="#38BDF8", font=FONTS["nav_item_active"])
            else:
                btn.config(bg=COLORS["bg_sidebar"], fg=COLORS["text_sidebar_muted"], font=FONTS["nav_item"])

        if view_name == "dashboard":
            v = AdminDashboardView(
                self.admin_content_area,
                on_navigate_customers=lambda: self._show_admin_view("customers"),
                on_navigate_fds=lambda: self._show_admin_view("fds"),
                on_navigate_calculator=lambda: self._show_admin_view("calculator"),
                on_add_customer=lambda: self._open_add_customer_modal(),
                on_add_fd=lambda: self._open_add_fd_modal(),
            )
            v.pack(fill="both", expand=True)
        elif view_name == "customers":
            v = CustomerManagementView(
                self.admin_content_area,
                on_open_portfolio=lambda cid: self._open_customer_portfolio_view(cid),
            )
            v.pack(fill="both", expand=True)
        elif view_name == "fds":
            v = FDManagementView(
                self.admin_content_area,
                on_view_customer=lambda cid: self._open_customer_portfolio_view(cid),
            )
            v.pack(fill="both", expand=True)
        elif view_name == "reports":
            v = ReportsView(self.admin_content_area)
            v.pack(fill="both", expand=True)
        elif view_name == "calculator":
            v = CalculatorView(self.admin_content_area)
            v.pack(fill="both", expand=True)

    def _open_customer_portfolio_view(self, customer_id: str):
        """Drill down into an individual customer's portfolio screen."""
        for child in self.admin_content_area.winfo_children():
            child.destroy()

        # Clear sidebar highlighting since in drilldown
        for btn in self.nav_buttons.values():
            btn.config(bg=COLORS["bg_sidebar"], fg=COLORS["text_sidebar_muted"], font=FONTS["nav_item"])

        portfolio_view = CustomerDashboardView(
            self.admin_content_area,
            customer_id=customer_id,
            is_admin_mode=True,
            on_back=lambda: self._show_admin_view("customers"),
            on_add_fd=lambda cid: self._open_add_fd_modal(preselected_customer_id=cid),
            on_edit_fd=lambda fid: self._open_edit_fd_modal(fid),
        )
        portfolio_view.pack(fill="both", expand=True)

    def _open_add_customer_modal(self):
        self._show_admin_view("customers")
        # Trigger add modal
        for child in self.admin_content_area.winfo_children():
            if isinstance(child, CustomerManagementView):
                child._open_add_customer_dialog()
                break

    def _open_add_fd_modal(self, preselected_customer_id: Optional[str] = None):
        self._show_admin_view("fds")
        for child in self.admin_content_area.winfo_children():
            if isinstance(child, FDManagementView):
                child._open_add_fd_dialog(preselected_customer_id=preselected_customer_id)
                break

    def _open_edit_fd_modal(self, fd_id: str):
        self._show_admin_view("fds")
        for child in self.admin_content_area.winfo_children():
            if isinstance(child, FDManagementView):
                child._open_edit_fd_dialog(fd_id=fd_id)
                break

    # =========================================================================
    # Customer Application Shell (Strict Data Isolation)
    # =========================================================================

    def _build_customer_shell(self):
        """Build personal workbench for individual logged-in customer."""
        self.current_shell = ttk.Frame(self, style="TFrame")
        self.current_shell.pack(fill="both", expand=True)

        # 1. Left Sidebar
        sidebar = tk.Frame(self.current_shell, bg=COLORS["bg_sidebar"], width=240)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Sidebar Header Branding
        brand_frame = tk.Frame(sidebar, bg=COLORS["bg_sidebar"], padx=18, pady=20)
        brand_frame.pack(fill="x")

        tk.Label(
            brand_frame,
            text="🏛  FD Manager",
            font=FONTS["app_title"],
            fg="#FFFFFF",
            bg=COLORS["bg_sidebar"],
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            brand_frame,
            text="My Fixed Deposit Portfolio",
            font=FONTS["app_subtitle"],
            fg=COLORS["text_sidebar_muted"],
            bg=COLORS["bg_sidebar"],
            anchor="w",
        ).pack(fill="x", pady=(2, 0))

        # Divider
        tk.Frame(sidebar, bg="#334155", height=1).pack(fill="x", pady=(0, 12))

        # Customer Badge
        cust_card = tk.Frame(sidebar, bg="#1E293B", padx=14, pady=10)
        cust_card.pack(fill="x", padx=14, pady=(0, 16))

        tk.Label(
            cust_card,
            text=f"👤  {session.full_name}",
            font=FONTS["body_bold"],
            fg="#FFFFFF",
            bg="#1E293B",
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            cust_card,
            text=f"Client ID: {session.customer_id}",
            font=FONTS["body_small"],
            fg="#34D399",  # Emerald green client badge
            bg="#1E293B",
            anchor="w",
        ).pack(fill="x")

        # Navigation Buttons Container
        self.cust_nav_container = tk.Frame(sidebar, bg=COLORS["bg_sidebar"])
        self.cust_nav_container.pack(fill="both", expand=True)

        self.cust_nav_buttons = {}
        cust_nav_items = [
            ("portfolio", "💼  My Portfolio", lambda: self._show_customer_view("portfolio")),
            ("calculator", "🧮  Maturity Calculator", lambda: self._show_customer_view("calculator")),
            ("reports", "📈  My Reports & Export", lambda: self._show_customer_view("reports")),
        ]

        for key, text, cmd in cust_nav_items:
            btn = tk.Button(
                self.cust_nav_container,
                text=text,
                font=FONTS["nav_item"],
                fg=COLORS["text_sidebar_muted"],
                bg=COLORS["bg_sidebar"],
                activebackground=COLORS["bg_sidebar_hover"],
                activeforeground="#FFFFFF",
                anchor="w",
                padx=18,
                pady=10,
                relief="flat",
                cursor="hand2",
                command=cmd,
            )
            btn.pack(fill="x", pady=1)
            self.cust_nav_buttons[key] = btn

        # Logout Button
        logout_btn = tk.Button(
            sidebar,
            text="🚪  Sign Out",
            font=FONTS["nav_item"],
            fg="#EF4444",
            bg=COLORS["bg_sidebar"],
            activebackground="#450A0A",
            activeforeground="#FCA5A5",
            anchor="w",
            padx=18,
            pady=12,
            relief="flat",
            cursor="hand2",
            command=self._handle_logout,
        )
        logout_btn.pack(side="bottom", fill="x", pady=12)

        # 2. Main Content Area
        self.customer_content_area = ttk.Frame(self.current_shell, style="TFrame")
        self.customer_content_area.pack(side="left", fill="both", expand=True)

        # Load initial view: strictly locked to authenticated customer_id
        self._show_customer_view("portfolio")

    def _show_customer_view(self, view_name: str):
        """Switch views in customer shell with guaranteed customer isolation."""
        for child in self.customer_content_area.winfo_children():
            child.destroy()

        for key, btn in self.cust_nav_buttons.items():
            if key == view_name:
                btn.config(bg="#1E293B", fg="#34D399", font=FONTS["nav_item_active"])
            else:
                btn.config(bg=COLORS["bg_sidebar"], fg=COLORS["text_sidebar_muted"], font=FONTS["nav_item"])

        if view_name == "portfolio":
            v = CustomerDashboardView(
                self.customer_content_area,
                customer_id=session.customer_id,
                is_admin_mode=False,
            )
            v.pack(fill="both", expand=True)
        elif view_name == "calculator":
            v = CalculatorView(self.customer_content_area)
            v.pack(fill="both", expand=True)
        elif view_name == "reports":
            v = ReportsView(self.customer_content_area)
            v.pack(fill="both", expand=True)


def main():
    """Application launcher."""
    app = FDManagerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
