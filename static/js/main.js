// Live Slot Booking Client logic
let selectedSlotId = null;
let selectedSlotPrice = 0.0;
let activeCancelBookingId = null;

document.addEventListener('DOMContentLoaded', () => {
    initBookingPage();
});

function initBookingPage() {
    const datePicker = document.getElementById('booking-date-picker');
    const courtSelect = document.getElementById('booking-court-select');

    if (!datePicker || !courtSelect) return;

    // Set default date to local TODAY (timezone aware)
    const today = new Date();
    const offset = today.getTimezoneOffset();
    const localToday = new Date(today.getTime() - (offset * 60 * 1000));
    const todayStr = localToday.toISOString().split('T')[0];
    datePicker.value = todayStr;
    datePicker.min = todayStr; // Prevent booking past dates

    // Hook listeners
    datePicker.addEventListener('change', loadLiveSlots);
    courtSelect.addEventListener('change', loadLiveSlots);

    // Initial Load
    loadLiveSlots();

    // Hook modal submission events
    const submitBtn = document.getElementById('btn-submit-booking-action');
    if (submitBtn) {
        submitBtn.addEventListener('click', processBookingSubmit);
    }

    const cancelConfirmBtn = document.getElementById('btn-submit-cancellation-action');
    if (cancelConfirmBtn) {
        cancelConfirmBtn.addEventListener('click', processCancellationSubmit);
    }
}

// Time Formatter for 12 hours representation
function formatTimeTo12Hour(timeStr) {
    if (!timeStr) return '';
    if (timeStr.includes(' - ')) {
        const parts = timeStr.split(' - ');
        return `${formatSingleTime(parts[0])} - ${formatSingleTime(parts[1])}`;
    }
    return formatSingleTime(timeStr);
}

function formatSingleTime(singleTimeStr) {
    const [hoursStr, minutesStr] = singleTimeStr.split(':');
    let hours = parseInt(hoursStr, 10);
    const minutes = minutesStr;
    const ampm = hours >= 12 ? 'PM' : 'AM';
    hours = hours % 12;
    hours = hours ? hours : 12;
    const formattedHours = hours < 10 ? '0' + hours : hours;
    return `${formattedHours}:${minutes} ${ampm}`;
}

// Fetch available slots from backend
function loadLiveSlots() {
    const datePicker = document.getElementById('booking-date-picker');
    const courtSelect = document.getElementById('booking-court-select');
    const slotsGrid = document.getElementById('slots-grid');
    const loadingSpinner = document.getElementById('slots-loading');
    const activeDateLabel = document.getElementById('current-selected-date-label');

    if (!datePicker || !courtSelect || !slotsGrid) return;

    const dateVal = datePicker.value;
    const courtVal = courtSelect.value;
    const courtName = courtSelect.options[courtSelect.selectedIndex]?.text || "Tristar Premier Court";

    // Format active date label nicely
    const dateObj = new Date(dateVal);
    activeDateLabel.innerText = dateObj.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });

    // Show spinner
    loadingSpinner.classList.remove('hidden');
    slotsGrid.innerHTML = '';

    fetch(`/api/slots?date=${dateVal}&court_id=${courtVal}`)
        .then(res => res.json())
        .then(data => {
            loadingSpinner.classList.add('hidden');
            if (data.success) {
                if (data.slots.length === 0) {
                    slotsGrid.innerHTML = '<div class="dashboard-empty-state"><i class="fa-solid fa-face-frown"></i><p>No slots found for this court configuration.</p></div>';
                    return;
                }

                // Check if selected date is a weekend (0 = Sunday, 6 = Saturday)
                const partsVal = dateVal.split('-');
                const dateObjVal = new Date(partsVal[0], partsVal[1] - 1, partsVal[2]);
                const isWeekendVal = (dateObjVal.getDay() === 0 || dateObjVal.getDay() === 6);

                data.slots.forEach(slot => {
                    const slotCard = document.createElement('div');
                    
                    // Style by status
                    slotCard.className = `slot-box status-${slot.status}`;
                    
                    let badgeLabel = 'Available';
                    let priceText = isWeekendVal ? `₹${slot.price} flat` : `₹${slot.price}/person`;
                    let clickHandler = '';

                    const timeRangeFormatted = `${formatTimeTo12Hour(slot.start_time)} - ${formatTimeTo12Hour(slot.end_time)}`;

                    let isSlotPast = false;
                    let isSlotStarted = false;
                    try {
                        const startDt = new Date(`${dateVal}T${slot.start_time}:00+05:30`);
                        let endDt = new Date(`${dateVal}T${slot.end_time}:00+05:30`);
                        
                        // Handle overnight slots (e.g. 11:00 PM to 01:00 AM)
                        if (endDt <= startDt) {
                            endDt.setDate(endDt.getDate() + 1);
                        }
                        
                        const now = new Date();
                        if (now >= startDt) {
                            isSlotStarted = true;
                        }
                        if (now >= endDt) {
                            isSlotPast = true;
                        }
                    } catch (e) {
                        console.error("Error parsing slot time", e);
                    }

                    if (slot.status === 'blocked') {
                        badgeLabel = slot.block_reason || 'Blocked';
                        priceText = '—';
                    } else if (slot.status === 'expired' || (isSlotPast && slot.status === 'available')) {
                        badgeLabel = 'Expired';
                        priceText = '—';
                        clickHandler = '';
                        slotCard.className = `slot-box status-expired`;
                    } else if (slot.status === 'booked_by_me') {
                        badgeLabel = 'Your Session';
                        if (isSlotStarted) {
                            clickHandler = '';
                            slotCard.style.cursor = 'default';
                            slotCard.style.opacity = '0.85';
                        } else {
                            clickHandler = `onclick="openCancelModal(${slot.booking_id}, '${courtName}', '${dateVal}', '${timeRangeFormatted}')"`;
                        }
                    } else if (slot.status === 'booked') {
                        badgeLabel = 'Booked';
                        priceText = 'Filled';
                    } else {
                        // Available and not past
                        clickHandler = `onclick="openBookingModal(${slot.slot_id}, '${courtName}', '${dateVal}', '${timeRangeFormatted}', ${slot.price})"`;
                    }

                    slotCard.innerHTML = `
                        <span class="slot-box-time"><i class="fa-regular fa-clock text-accent"></i> ${timeRangeFormatted}</span>
                        <span class="slot-box-price">${priceText}</span>
                        <span class="slot-box-status">${badgeLabel}</span>
                    `;
                    
                    if (clickHandler) {
                        slotCard.setAttribute('onclick', slotCard.getAttribute('onclick') || '');
                        slotCard.onclick = new Function(clickHandler.replace('onclick=', '').replace(/"/g, ''));
                    }

                    slotsGrid.appendChild(slotCard);
                });
            } else {
                window.showToast(data.message || "Failed to load slots availability.", 'error');
            }
        })
        .catch(err => {
            loadingSpinner.classList.add('hidden');
            console.error("Error loading slots:", err);
            window.showToast("Connection to court API failed.", 'error');
        });
}

// Modal open controllers
function openBookingModal(slotId, courtName, dateStr, timeStr, price) {
    selectedSlotId = slotId;
    selectedSlotPrice = price;

    document.getElementById('modal-summary-court').innerText = courtName;
    document.getElementById('modal-summary-date').innerText = dateStr;
    document.getElementById('modal-summary-time').innerText = timeStr;

    // Check if the booking date is a weekend (0 = Sunday, 6 = Saturday)
    const parts = dateStr.split('-');
    const dateObj = new Date(parts[0], parts[1] - 1, parts[2]);
    const isWeekend = (dateObj.getDay() === 0 || dateObj.getDay() === 6);

    const membersContainer = document.getElementById('modal-members-container');
    if (isWeekend) {
        if (membersContainer) membersContainer.classList.add('hidden');
        document.getElementById('booking-members-count').value = 1; // Default/Placeholder limit
        document.getElementById('modal-summary-price').innerText = `₹300.00`;
    } else {
        if (membersContainer) membersContainer.classList.remove('hidden');
        document.getElementById('booking-members-count').value = 2; // Default to 2 players
        updateModalPriceSummary(2);
    }

    document.getElementById('modal-confirm-booking').classList.remove('hidden');
}

function updateModalPriceSummary(players) {
    const total = selectedSlotPrice * players;
    document.getElementById('modal-summary-price').innerText = `₹${total.toFixed(2)}`;
}

function openCancelModal(bookingId, courtName, dateStr, timeStr) {
    activeCancelBookingId = bookingId;

    document.getElementById('cancel-summary-court').innerText = courtName;
    document.getElementById('cancel-summary-date').innerText = dateStr;
    document.getElementById('cancel-summary-time').innerText = timeStr;

    document.getElementById('modal-cancel-booking').classList.remove('hidden');
}

function closeBookingModal(type) {
    if (type === 'confirm') {
        document.getElementById('modal-confirm-booking').classList.add('hidden');
        selectedSlotId = null;
    } else {
        document.getElementById('modal-cancel-booking').classList.add('hidden');
        activeCancelBookingId = null;
    }
}

// Counter helper for player size selection
function adjustPlayers(val) {
    const input = document.getElementById('booking-members-count');
    if (!input) return;

    let currentVal = parseInt(input.value) || 2;
    currentVal += val;

    if (currentVal >= 1) {
        input.value = currentVal;
        updateModalPriceSummary(currentVal);
    }
}

// Submit payment / Booking Reservation
function processBookingSubmit() {
    if (!selectedSlotId) return;

    const dateVal = document.getElementById('booking-date-picker').value;
    const courtVal = document.getElementById('booking-court-select').value;
    const playersCount = parseInt(document.getElementById('booking-members-count').value) || 2;

    const payload = {
        court_id: parseInt(courtVal),
        slot_id: selectedSlotId,
        date: dateVal,
        num_members: playersCount
    };

    // Disable action button to prevent click spamming
    const submitBtn = document.getElementById('btn-submit-booking-action');
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Reserving...';

    fetch('/api/book', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fa-solid fa-credit-card"></i> Pay & Book Now';
        closeBookingModal('confirm');

        if (data.success) {
            sessionStorage.setItem('booking_success_msg', data.message);
            const amount = (data.booking && data.booking.total_price) ? data.booking.total_price : 0;
            const bookingId = (data.booking && data.booking.id) ? data.booking.id : null;
            window.showUPIPaymentModal(amount, '/profile', bookingId);
        } else {
            window.showToast(data.message, 'error');
        }
    })
    .catch(err => {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fa-solid fa-credit-card"></i> Pay & Book Now';
        closeBookingModal('confirm');
        console.error(err);
        window.showToast("Reserve request timed out.", 'error');
    });
}

// Submit Cancellation requests
function processCancellationSubmit() {
    if (!activeCancelBookingId) return;

    const cancelBtn = document.getElementById('btn-submit-cancellation-action');
    cancelBtn.disabled = true;
    cancelBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Cancelling...';

    fetch('/api/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ booking_id: activeCancelBookingId })
    })
    .then(res => res.json())
    .then(data => {
        cancelBtn.disabled = false;
        cancelBtn.innerHTML = '<i class="fa-solid fa-trash-can"></i> Confirm Cancellation';
        closeBookingModal('cancel');

        if (data.success) {
            window.showToast("Your booking was cancelled.", 'success');
            loadLiveSlots();
        } else {
            window.showToast(data.message, 'error');
        }
    })
    .catch(err => {
        cancelBtn.disabled = false;
        cancelBtn.innerHTML = '<i class="fa-solid fa-trash-can"></i> Confirm Cancellation';
        closeBookingModal('cancel');
        console.error(err);
        window.showToast("Failed to process cancellation.", 'error');
    });
}
