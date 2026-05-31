"""Gmail SMTP notifier via aiosmtplib."""
from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from ..models.schemas import CarListingRead, LeasingAnalysisRead, ScoredListingRead
from .base import BaseNotifier

logger = logging.getLogger(__name__)

GMAIL_HOST = "smtp.gmail.com"
GMAIL_PORT = 587


class GmailNotifier(BaseNotifier):
    channel_name = "gmail"

    def __init__(self, user: str, app_password: str, to_address: str) -> None:
        self._user = user
        self._password = app_password
        self._to = to_address

    async def send(
        self,
        listing: CarListingRead,
        score: ScoredListingRead,
        leasing: LeasingAnalysisRead | None,
    ) -> bool:
        subject = (
            f"[Car Hunter] {listing.make.title()} {listing.model.title()} {listing.year} "
            f"— {listing.price_pln:,.0f} PLN | Score {score.total_score}/10"
        )
        html_body = self._build_html(listing, score, leasing)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._user
        msg["To"] = self._to
        msg.attach(MIMEText(self.format_text(listing, score, leasing), "plain"))
        msg.attach(MIMEText(html_body, "html"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=GMAIL_HOST,
                port=GMAIL_PORT,
                username=self._user,
                password=self._password,
                start_tls=True,
            )
            logger.info("[gmail] Alert sent for listing %s", listing.id)
            return True
        except Exception as exc:
            logger.error("[gmail] Failed to send alert: %s", exc)
            return False

    def _build_html(
        self,
        listing: CarListingRead,
        score: ScoredListingRead,
        leasing: LeasingAnalysisRead | None,
    ) -> str:
        score_color = "#27ae60" if score.total_score >= 8 else "#f39c12" if score.total_score >= 6 else "#e74c3c"
        suspicious_row = (
            '<tr><td colspan="2" style="color:#e74c3c;font-weight:bold;">'
            "⚠️ Price suspiciously low — verify carefully!</td></tr>"
            if score.is_suspicious else ""
        )
        deviation_text = ""
        if score.price_deviation_pct is not None:
            sign = "+" if score.price_deviation_pct > 0 else ""
            deviation_text = f"{sign}{score.price_deviation_pct:.1f}% vs market avg"

        leasing_section = ""
        if leasing:
            leasing_section = f"""
            <h3 style="color:#2c3e50;">📋 Leasing Estimate</h3>
            <table style="border-collapse:collapse;width:100%;max-width:500px;">
              <tr style="background:#ecf0f1;">
                <td style="padding:8px;border:1px solid #bdc3c7;">Down payment</td>
                <td style="padding:8px;border:1px solid #bdc3c7;font-weight:bold;">
                  {leasing.down_payment_pln:,.0f} PLN</td>
              </tr>
              <tr>
                <td style="padding:8px;border:1px solid #bdc3c7;">Monthly payment</td>
                <td style="padding:8px;border:1px solid #bdc3c7;font-weight:bold;">
                  {leasing.monthly_payment_pln:,.0f} PLN</td>
              </tr>
              <tr style="background:#ecf0f1;">
                <td style="padding:8px;border:1px solid #bdc3c7;">Buyout value</td>
                <td style="padding:8px;border:1px solid #bdc3c7;font-weight:bold;">
                  {leasing.buyout_value_pln:,.0f} PLN</td>
              </tr>
              <tr>
                <td style="padding:8px;border:1px solid #bdc3c7;">Total cost ({leasing.term_months} months)</td>
                <td style="padding:8px;border:1px solid #bdc3c7;font-weight:bold;">
                  {leasing.total_cost_pln:,.0f} PLN</td>
              </tr>
              <tr style="background:#ecf0f1;">
                <td style="padding:8px;border:1px solid #bdc3c7;">Cost per year</td>
                <td style="padding:8px;border:1px solid #bdc3c7;font-weight:bold;">
                  {leasing.cost_per_year_pln:,.0f} PLN</td>
              </tr>
              <tr>
                <td style="padding:8px;border:1px solid #bdc3c7;">Est. maintenance/year</td>
                <td style="padding:8px;border:1px solid #bdc3c7;font-weight:bold;">
                  {leasing.estimated_maintenance_yearly_pln:,.0f} PLN</td>
              </tr>
            </table>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <body style="font-family:Arial,sans-serif;color:#2c3e50;max-width:700px;margin:0 auto;padding:20px;">
          <div style="background:{score_color};color:white;padding:15px;border-radius:8px;margin-bottom:20px;">
            <h2 style="margin:0;">🚗 New Car Found!</h2>
            <p style="margin:5px 0 0;font-size:1.2em;">{listing.title}</p>
          </div>

          <table style="border-collapse:collapse;width:100%;max-width:500px;margin-bottom:20px;">
            <tr style="background:#f8f9fa;">
              <td style="padding:10px;border:1px solid #dee2e6;font-weight:bold;">Price</td>
              <td style="padding:10px;border:1px solid #dee2e6;font-size:1.3em;color:{score_color};">
                <b>{listing.price_pln:,.0f} PLN</b></td>
            </tr>
            <tr>
              <td style="padding:10px;border:1px solid #dee2e6;font-weight:bold;">Year</td>
              <td style="padding:10px;border:1px solid #dee2e6;">{listing.year}</td>
            </tr>
            <tr style="background:#f8f9fa;">
              <td style="padding:10px;border:1px solid #dee2e6;font-weight:bold;">Mileage</td>
              <td style="padding:10px;border:1px solid #dee2e6;">{listing.mileage_km:,} km</td>
            </tr>
            <tr>
              <td style="padding:10px;border:1px solid #dee2e6;font-weight:bold;">Fuel</td>
              <td style="padding:10px;border:1px solid #dee2e6;">{listing.fuel_type.capitalize()}</td>
            </tr>
            <tr style="background:#f8f9fa;">
              <td style="padding:10px;border:1px solid #dee2e6;font-weight:bold;">Transmission</td>
              <td style="padding:10px;border:1px solid #dee2e6;">{listing.transmission.capitalize()}</td>
            </tr>
            <tr>
              <td style="padding:10px;border:1px solid #dee2e6;font-weight:bold;">Seller</td>
              <td style="padding:10px;border:1px solid #dee2e6;">{listing.seller_type.capitalize()}</td>
            </tr>
            <tr style="background:#f8f9fa;">
              <td style="padding:10px;border:1px solid #dee2e6;font-weight:bold;">Location</td>
              <td style="padding:10px;border:1px solid #dee2e6;">{listing.location or "N/A"}</td>
            </tr>
            <tr>
              <td style="padding:10px;border:1px solid #dee2e6;font-weight:bold;">Reliability score</td>
              <td style="padding:10px;border:1px solid #dee2e6;color:{score_color};font-weight:bold;">
                {score.total_score}/10 {deviation_text}</td>
            </tr>
            {suspicious_row}
          </table>

          {leasing_section}

          <p style="margin-top:25px;">
            <a href="{listing.url}" style="background:{score_color};color:white;padding:12px 24px;
               text-decoration:none;border-radius:6px;font-weight:bold;">
              View Listing →
            </a>
          </p>
          <p style="color:#95a5a6;font-size:0.85em;margin-top:30px;">
            Sent by Car Hunter | Source: {listing.source}
          </p>
        </body>
        </html>
        """
