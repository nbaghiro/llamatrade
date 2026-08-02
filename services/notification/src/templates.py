"""Per-category rendering: NotificationEvent -> title, message, email subject.

Producers send machine fields only; all copy lives here so template changes
never touch a producing service. Missing fields render as empty and the
templates are written to degrade readably.
"""

from __future__ import annotations

from dataclasses import dataclass

from llamatrade_proto.generated import events_pb2

_E = events_pb2


@dataclass(frozen=True)
class Rendered:
    title: str
    message: str
    cta_url: str | None = None
    cta_label: str | None = None

    @property
    def subject(self) -> str:
        return f"LlamaTrade: {self.title}"

    @property
    def text_body(self) -> str:
        """The plain-text part; a CTA link must survive text-only clients."""
        if self.cta_url is None:
            return self.message
        return f"{self.message}\n\n{self.cta_label or 'Open'}: {self.cta_url}"


def _sym(event: events_pb2.NotificationEvent) -> str:
    return f" {event.symbol}" if event.symbol else ""


def _reason(event: events_pb2.NotificationEvent) -> str:
    return f": {event.reason}" if event.reason else "."


def _amount(event: events_pb2.NotificationEvent) -> str:
    return f" (${event.amount})" if event.amount else ""


def render(event: events_pb2.NotificationEvent) -> Rendered:
    c = event.category
    e = _E
    if c == e.NOTIFICATION_CATEGORY_SLEEVE_FROZEN:
        return Rendered(
            "Sleeve frozen",
            f"A sleeve on your account was frozen{_reason(event)} "
            "New orders on it are rejected until the discrepancy is resolved.",
        )
    if c == e.NOTIFICATION_CATEGORY_FILL_QUARANTINED:
        return Rendered(
            "Fill quarantined",
            f"A fill could not be booked{_reason(event)} "
            "It is parked for operator review and your ledger is unchanged.",
        )
    if c == e.NOTIFICATION_CATEGORY_EXTERNAL_TRADE_ADOPTED:
        return Rendered(
            "External trade detected",
            f"A holding{_sym(event)} not placed by LlamaTrade was found at your broker "
            "and was adopted into your Unmanaged sleeve.",
        )
    if c == e.NOTIFICATION_CATEGORY_CORPORATE_ACTION_PROPOSED:
        return Rendered(
            "Corporate action pending",
            f"A corporate action{_sym(event)}{_amount(event)} was detected and awaits "
            "review before it is applied to your ledger.",
        )
    if c == e.NOTIFICATION_CATEGORY_CORPORATE_ACTION_APPLIED:
        return Rendered(
            "Corporate action applied",
            f"A corporate action{_sym(event)}{_amount(event)} was applied to your ledger.",
        )
    if c == e.NOTIFICATION_CATEGORY_ORDER_FILLED:
        return Rendered("Order filled", f"Your order{_sym(event)}{_amount(event)} filled.")
    if c == e.NOTIFICATION_CATEGORY_ORDER_REJECTED:
        return Rendered("Order rejected", f"Your order{_sym(event)} was rejected{_reason(event)}")
    if c == e.NOTIFICATION_CATEGORY_POSITION_OPENED:
        return Rendered("Position opened", f"A position{_sym(event)}{_amount(event)} was opened.")
    if c == e.NOTIFICATION_CATEGORY_POSITION_CLOSED:
        return Rendered("Position closed", f"A position{_sym(event)}{_amount(event)} was closed.")
    if c == e.NOTIFICATION_CATEGORY_POSITION_DRIFT:
        return Rendered(
            "Position drift",
            f"Your broker and LlamaTrade disagree on a position{_sym(event)}{_reason(event)}",
        )
    if c == e.NOTIFICATION_CATEGORY_RISK_BREACH:
        return Rendered(
            "Order blocked by risk gate", f"An order{_sym(event)} was blocked{_reason(event)}"
        )
    if c == e.NOTIFICATION_CATEGORY_EVALUATION_STALLED:
        return Rendered(
            "Strategy evaluation stalled",
            f"A live strategy has not evaluated recently{_reason(event)} "
            "Positions are unchanged while the gate is closed.",
        )
    if c == e.NOTIFICATION_CATEGORY_SYMBOL_NOT_TRADABLE:
        return Rendered(
            "Symbol not tradable",
            f"A symbol{_sym(event)} in a live strategy is halted or delisted{_reason(event)} "
            "A decision is needed on the affected position.",
        )
    if c == e.NOTIFICATION_CATEGORY_CONNECTION_LOST:
        return Rendered("Broker connection lost", f"A live data connection dropped{_reason(event)}")
    if c == e.NOTIFICATION_CATEGORY_STRATEGY_ERROR:
        return Rendered("Strategy error", f"A live strategy hit an error{_reason(event)}")
    if c == e.NOTIFICATION_CATEGORY_SESSION_STARTED:
        return Rendered("Trading session started", "A live trading session started.")
    if c == e.NOTIFICATION_CATEGORY_SESSION_STOPPED:
        return Rendered(
            "Trading session stopped", f"A live trading session stopped{_reason(event)}"
        )
    if c == e.NOTIFICATION_CATEGORY_SESSION_ERROR:
        return Rendered("Trading session failed", f"A live trading session failed{_reason(event)}")
    if c == e.NOTIFICATION_CATEGORY_CIRCUIT_BREAKER_TRIGGERED:
        return Rendered(
            "Circuit breaker triggered",
            f"Trading was halted by a circuit breaker{_reason(event)}",
        )
    if c == e.NOTIFICATION_CATEGORY_CIRCUIT_BREAKER_RESET:
        return Rendered("Circuit breaker reset", "Trading resumed after a circuit-breaker halt.")
    if c == e.NOTIFICATION_CATEGORY_STOP_LOSS_HIT:
        return Rendered("Stop loss hit", f"A stop loss{_sym(event)}{_amount(event)} executed.")
    if c == e.NOTIFICATION_CATEGORY_TAKE_PROFIT_HIT:
        return Rendered("Take profit hit", f"A take profit{_sym(event)}{_amount(event)} executed.")
    if c == e.NOTIFICATION_CATEGORY_RECONCILIATION_DRIFT:
        return Rendered(
            "Reconciliation drift",
            f"Reconciliation found a discrepancy{_sym(event)}{_reason(event)}",
        )
    if c == e.NOTIFICATION_CATEGORY_EXECUTION_STARTED:
        return Rendered("Strategy deployed", "Your strategy is funded and running.")
    if c == e.NOTIFICATION_CATEGORY_EXECUTION_STOPPED:
        return Rendered("Strategy stopped", f"Your strategy stopped{_reason(event)}")
    if c == e.NOTIFICATION_CATEGORY_FUNDING_FAILED:
        return Rendered(
            "Deploy failed at funding",
            f"Your strategy could not be funded and did not go live{_reason(event)}",
        )
    if c == e.NOTIFICATION_CATEGORY_SLEEVE_RELEASE_DEFERRED:
        return Rendered(
            "Capital release delayed",
            "Your stopped strategy's capital could not be released yet. "
            "A background sweep keeps retrying; no action is needed, but we are flagging it.",
        )
    if c == e.NOTIFICATION_CATEGORY_EXECUTION_CANCELLED:
        return Rendered(
            "Execution cancelled",
            f"A pending execution was cancelled{_reason(event)}",
        )
    if c == e.NOTIFICATION_CATEGORY_PLAN_LIMIT_REACHED:
        return Rendered(
            "Plan limit reached",
            f"You hit a plan limit{_reason(event)} Upgrade to raise it.",
        )
    if c == e.NOTIFICATION_CATEGORY_BACKTEST_COMPLETED:
        return Rendered("Backtest completed", "Your backtest finished and results are ready.")
    if c == e.NOTIFICATION_CATEGORY_BACKTEST_FAILED:
        return Rendered("Backtest failed", f"Your backtest did not complete{_reason(event)}")
    if c == e.NOTIFICATION_CATEGORY_PAYMENT_SUCCEEDED:
        return Rendered(
            "Payment received",
            f"Your subscription payment{_amount(event)} was received. Thank you.",
        )
    if c == e.NOTIFICATION_CATEGORY_PAYMENT_FAILED:
        return Rendered(
            "Payment failed",
            "Your subscription payment failed. Update your payment method to avoid "
            "losing the ability to start live strategies.",
        )
    if c == e.NOTIFICATION_CATEGORY_TRIAL_ENDING:
        return Rendered(
            "Trial ending soon",
            "Your trial ends soon. Add a payment method to keep your plan's features.",
        )
    if c == e.NOTIFICATION_CATEGORY_SUBSCRIPTION_UPDATED:
        return Rendered("Subscription updated", f"Your subscription changed{_reason(event)}")
    if c == e.NOTIFICATION_CATEGORY_SUBSCRIPTION_CANCELED:
        return Rendered(
            "Subscription canceled",
            "Your subscription was canceled. Running strategies keep trading; new live "
            "deploys are blocked.",
        )
    if c == e.NOTIFICATION_CATEGORY_WELCOME:
        return Rendered(
            "Welcome to LlamaTrade",
            "Your account is ready. Build a strategy, backtest it, and deploy when ready.",
        )
    if c == e.NOTIFICATION_CATEGORY_PASSWORD_CHANGED:
        return Rendered(
            "Your password was changed",
            "Your password was changed and all sessions were signed out. "
            "If this was not you, reset your password immediately.",
        )
    if c == e.NOTIFICATION_CATEGORY_ACCOUNT_LOCKED:
        return Rendered(
            "Sign-in attempts blocked",
            "Repeated failed sign-in attempts on your account were rate limited. "
            "If this was not you, consider changing your password.",
        )
    if c == e.NOTIFICATION_CATEGORY_EMAIL_VERIFICATION:
        link = event.extra.get("link", "")
        return Rendered(
            "Verify your email",
            "Confirm your email address to finish setting up your account."
            if link
            else f"Confirm your email address{_reason(event)}",
            cta_url=link or None,
            cta_label="Verify email" if link else None,
        )
    if c == e.NOTIFICATION_CATEGORY_PASSWORD_RESET:
        link = event.extra.get("link", "")
        return Rendered(
            "Reset your password",
            "A password reset was requested for your account. The link expires in one hour; "
            "if this was not you, ignore this email."
            if link
            else f"A password reset was requested for your account{_reason(event)}",
            cta_url=link or None,
            cta_label="Reset password" if link else None,
        )
    if c == e.NOTIFICATION_CATEGORY_CONFIRMATION_PENDING:
        return Rendered(
            "Copilot action awaiting approval",
            "A copilot proposal is waiting for your confirmation.",
        )
    if c == e.NOTIFICATION_CATEGORY_PRICE_ALERT_TRIGGERED:
        return Rendered(
            "Price alert triggered", f"Your alert{_sym(event)} triggered{_reason(event)}"
        )
    if c == e.NOTIFICATION_CATEGORY_WEBHOOK_DISABLED:
        return Rendered(
            "Webhook disabled",
            f"A webhook endpoint kept failing and was disabled{_reason(event)} "
            "Re-enable it from Settings once fixed.",
        )
    return Rendered("Notification", event.reason or "You have a new notification.")
