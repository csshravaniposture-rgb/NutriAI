document.addEventListener("DOMContentLoaded", function () {

    const notificationBtn =
        document.getElementById("enableNotificationsBtn");

    const notificationCard =
        document.getElementById("notificationCard");

    if (!notificationBtn) {
        console.error("Notification button not found.");
        return;
    }


    // ==========================================
    // HIDE THE CARD (collapses smoothly via CSS)
    // ==========================================

    function hideNotificationCard() {

        if (notificationCard) {
            notificationCard.classList.add("is-hidden");
        }
    }


    // ==========================================
    // CHECK BROWSER SUPPORT
    // ==========================================

    if (!("Notification" in window)) {

        notificationBtn.textContent =
            "Notifications Not Supported";

        notificationBtn.disabled = true;

        return;
    }


    // ==========================================
    // UPDATE BUTTON STATE
    // ==========================================

    function updateNotificationButton() {

        if (Notification.permission === "granted") {

            notificationBtn.textContent =
                "✓ Notifications Enabled";

            notificationBtn.classList.add("enabled");

            // Already granted (e.g. on page reload) — hide immediately
            hideNotificationCard();

        }

        else if (Notification.permission === "denied") {

            notificationBtn.textContent =
                "Notifications Blocked";

            notificationBtn.classList.add("blocked");

            // Card stays visible so the user can see how to unblock

        }

        else {

            notificationBtn.textContent =
                "Enable Notifications";

        }
    }


    updateNotificationButton();


    // ==========================================
    // ENABLE NOTIFICATIONS
    // ==========================================

    notificationBtn.addEventListener(
        "click",
        async function () {

            console.log("Notification button clicked");


            // Already enabled
            if (Notification.permission === "granted") {

                showTestNotification();

                return;
            }


            // Browser permission request
            try {

                const permission =
                    await Notification.requestPermission();


                console.log(
                    "Notification permission:",
                    permission
                );


                if (permission === "granted") {

                    notificationBtn.textContent =
                        "✓ Notifications Enabled";

                    notificationBtn.classList.add(
                        "enabled"
                    );


                    // Show confirmation notification
                    showTestNotification();


                    // Collapse the "Stay on Track" card away
                    hideNotificationCard();


                }

                else if (permission === "denied") {

                    notificationBtn.textContent =
                        "Notifications Blocked";

                    notificationBtn.classList.add(
                        "blocked"
                    );


                    alert(
                        "Notifications are blocked. " +
                        "Please allow notifications for NutriAI " +
                        "from your browser settings."
                    );

                }

                else {

                    notificationBtn.textContent =
                        "Enable Notifications";

                }

            }

            catch (error) {

                console.error(
                    "Notification error:",
                    error
                );

                alert(
                    "Unable to enable notifications."
                );

            }

        }
    );


    // ==========================================
    // TEST NOTIFICATION
    // ==========================================

    function showTestNotification() {

        if (Notification.permission !== "granted") {
            return;
        }


        const notification =
            new Notification(
                "🥗 NutriAI Notifications Enabled",
                {
                    body:
                        "You'll receive meal, hydration and nutrition reminders."
                }
            );


        notification.onclick = function () {

            window.focus();

            notification.close();

        };

    }


    // ==========================================
    // MEAL REMINDER
    // ==========================================

    function mealReminder() {

        if (Notification.permission !== "granted") {
            return;
        }


        new Notification(
            "🍽️ NutriAI Meal Reminder",
            {
                body:
                    "It's time to check your NutriAI meal plan."
            }
        );

    }


    // ==========================================
    // HYDRATION REMINDER
    // ==========================================

    function hydrationReminder() {

        if (Notification.permission !== "granted") {
            return;
        }


        new Notification(
            "💧 Stay Hydrated",
            {
                body:
                    "Time to drink some water and stay hydrated!"
            }
        );

    }


    // ==========================================
    // NUTRITION REMINDER
    // ==========================================

    function nutritionReminder() {

        if (Notification.permission !== "granted") {
            return;
        }


        new Notification(
            "🥗 Nutrition Check",
            {
                body:
                    "Don't forget to keep track of today's nutrition."
            }
        );

    }


    // ==========================================
    // BELL ICON (TOPBAR)
    // ==========================================

    const bellBtn = document.getElementById("notificationBell");

    if (bellBtn) {

        bellBtn.addEventListener("click", function () {

            if (Notification.permission === "granted") {
                nutritionReminder();
            }
            else {
                alert("Please enable notifications first.");
            }

        });
    }


    // ==========================================
    // REMINDER SYSTEM
    // ==========================================

    // These are demo intervals.
    // Change them later to actual meal timings.

    setInterval(
        function () {

            if (Notification.permission === "granted") {
                hydrationReminder();
            }

        },
        60 * 60 * 1000
    );


});