import arrow
from flask import render_template, flash, redirect, url_for
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, validators

from app.config import ADMIN_EMAIL
from app.dashboard.base import dashboard_bp
from app.email_utils import send_email
from app.extensions import db
from app.models import (
    ManualSubscription,
    Coupon,
    Subscription,
    AppleSubscription,
    CoinbaseSubscription,
)


class CouponForm(FlaskForm):
    code = StringField("Coupon Code", validators=[validators.DataRequired()])


@dashboard_bp.route("/coupon", methods=["GET", "POST"])
@login_required
def coupon_route():
    # handle case user already has an active subscription via another channel (Paddle, Apple, etc)
    can_use_coupon = True

    if current_user.lifetime:
        can_use_coupon = False

    sub: Subscription = current_user.get_subscription()
    if sub:
        can_use_coupon = False

    apple_sub: AppleSubscription = AppleSubscription.get_by(user_id=current_user.id)
    if apple_sub and apple_sub.is_valid():
        can_use_coupon = False

    coinbase_subscription: CoinbaseSubscription = CoinbaseSubscription.get_by(
        user_id=current_user.id
    )
    if coinbase_subscription and coinbase_subscription.is_active():
        can_use_coupon = False

    if not can_use_coupon:
        flash("You already have another subscription.", "warning")
        return redirect(url_for("dashboard.index"))

    coupon_form = CouponForm()

    if coupon_form.validate_on_submit():
        code = coupon_form.code.data

        coupon: Coupon = Coupon.get_by(code=code)
        if coupon and not coupon.used:
            coupon.used_by_user_id = current_user.id
            coupon.used = True
            db.session.commit()

            manual_sub: ManualSubscription = ManualSubscription.get_by(
                user_id=current_user.id
            )
            if manual_sub:
                # renew existing subscription
                if manual_sub.end_at > arrow.now():
                    manual_sub.end_at = manual_sub.end_at.shift(years=coupon.nb_year)
                else:
                    manual_sub.end_at = arrow.now().shift(years=coupon.nb_year, days=1)
                db.session.commit()
                flash(
                    f"Your current subscription is extended to {manual_sub.end_at.humanize()}",
                    "success",
                )
            else:
                ManualSubscription.create(
                    user_id=current_user.id,
                    end_at=arrow.now().shift(years=coupon.nb_year, days=1),
                    comment="using coupon code",
                    is_giveaway=False,
                    commit=True,
                )
                flash(
                    f"Your account has been upgraded to Premium, thanks for your support!",
                    "success",
                )

            # notify admin
            send_email(
                ADMIN_EMAIL,
                subject=f"User {current_user} applies the coupon",
                plaintext="",
                html="",
            )

            return redirect(url_for("dashboard.index"))

        else:
            flash(f"Code *{code}* expired or invalid", "warning")

    return render_template("dashboard/coupon.html", coupon_form=coupon_form)
