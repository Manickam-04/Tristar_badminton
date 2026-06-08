// Academy Admin Dashboard Controller logic
let activeEditSlotId = null;
let activeReplyQueryId = null;

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

function convert12HourTo24Hour(time12h) {
    if (!time12h) return null;
    time12h = time12h.trim().toUpperCase();
    const matches = time12h.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/);
    if (!matches) return null;
    
    let hours = parseInt(matches[1], 10);
    const minutes = matches[2];
    const ampm = matches[3];
    
    if (ampm === 'PM' && hours < 12) hours += 12;
    if (ampm === 'AM' && hours === 12) hours = 0;
    
    const formattedHours = hours < 10 ? '0' + hours : hours;
    return `${formattedHours}:${minutes}`;
}

function formatWeeklyString(weekKey) {
    if (!weekKey || !weekKey.includes('-')) return weekKey;
    const parts = weekKey.split('-');
    const year = parseInt(parts[0], 10);
    const weekNum = parseInt(parts[1], 10);

    const jan1 = new Date(year, 0, 1);
    let daysToFirstMonday = (1 - jan1.getDay() + 7) % 7;
    if (daysToFirstMonday === 0 && jan1.getDay() !== 1) {
        daysToFirstMonday = 7;
    }
    const firstMonday = new Date(year, 0, 1 + daysToFirstMonday);
    
    let targetMonday;
    if (weekNum === 0) {
        targetMonday = jan1;
    } else {
        targetMonday = new Date(firstMonday.getTime() + (weekNum - 1) * 7 * 24 * 60 * 60 * 1000);
    }

    const months = [
        "January", "February", "March", "April", "May", "June", 
        "July", "August", "September", "October", "November", "December"
    ];
    const monthName = months[targetMonday.getMonth()];
    const day = targetMonday.getDate();
    const weekOfMonth = Math.ceil(day / 7);

    return `${monthName} week ${weekOfMonth} (${year})`;
}

document.addEventListener('DOMContentLoaded', () => {
    initAdminDashboard();
});

function initAdminDashboard() {
    const tabMetricsBtn = document.getElementById('tab-metrics-btn');
    if (!tabMetricsBtn) return; // Not on admin page

    // Parse 'tab' from query parameter to support direct menu links
    const urlParams = new URLSearchParams(window.location.search);
    const tabParam = urlParams.get('tab');
    
    const validTabs = ['bookings', 'slots', 'queries', 'metrics'];
    if (tabParam && validTabs.includes(tabParam)) {
        switchAdminTab(tabParam);
    } else {
        // Initial Load - Booking Logs
        switchAdminTab('bookings');
    }
    
    // Poll/Check for pending complaints to update query badge count
    updateQueryBadgeCount();
    
    // Setup Admin slot controls event bindings
    const courtSelect = document.getElementById('admin-court-select');
    const dateSelect = document.getElementById('admin-date-select');
    if (courtSelect && dateSelect) {
        courtSelect.addEventListener('change', loadAdminSlots);
        dateSelect.addEventListener('change', loadAdminSlots);
    }
}

// Global Tab Manager
function switchAdminTab(tab) {
    const panels = ['metrics', 'slots', 'bookings', 'queries', 'memberships'];
    
    panels.forEach(p => {
        const btn = document.getElementById(`tab-${p}-btn`);
        const panel = document.getElementById(`admin-panel-${p}`);
        if (btn && panel) {
            if (p === tab) {
                btn.classList.add('active');
                panel.classList.remove('hidden');
            } else {
                btn.classList.remove('active');
                panel.classList.hide ? panel.classList.hide() : panel.classList.add('hidden');
            }
        }
    });

    // Action routers on tab activate
    if (tab === 'metrics') {
        loadMetricsAndReports();
    } else if (tab === 'slots') {
        loadAdminCourts();
    } else if (tab === 'bookings') {
        loadBookingsLog();
    } else if (tab === 'queries') {
        loadCustomerQueries();
    } else if (tab === 'memberships') {
        loadMembershipsLog();
    }
}

// 1. Statistics & Reports Loader
function loadMetricsAndReports() {
    fetch('/admin/api/reports')
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                const rep = data.reports;
                // Metrics
                document.getElementById('stat-revenue').innerText = `₹${rep.metrics.total_revenue.toFixed(2)}`;
                document.getElementById('stat-bookings').innerText = rep.metrics.total_bookings;
                document.getElementById('stat-cancellations').innerText = rep.metrics.total_cancellations;

                // Monthly Table
                const monthlyBody = document.getElementById('report-monthly-body');
                monthlyBody.innerHTML = '';
                if (rep.monthly.length === 0) {
                    monthlyBody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">No monthly bookings registered.</td></tr>';
                } else {
                    rep.monthly.forEach(m => {
                        monthlyBody.innerHTML += `
                            <tr>
                                <td><strong>${m.month}</strong></td>
                                <td>${m.bookings} slots</td>
                                <td class="text-accent"><strong>₹${m.revenue.toFixed(2)}</strong></td>
                            </tr>
                        `;
                    });
                }

                // Weekly Table
                const weeklyBody = document.getElementById('report-weekly-body');
                weeklyBody.innerHTML = '';
                if (rep.weekly.length === 0) {
                    weeklyBody.innerHTML = '<tr><td colspan="3" class="text-center text-muted">No weekly activity log found.</td></tr>';
                } else {
                    rep.weekly.forEach(w => {
                        weeklyBody.innerHTML += `
                            <tr>
                                <td><strong>${formatWeeklyString(w.week)}</strong></td>
                                <td>${w.bookings} sessions</td>
                                <td class="text-accent"><strong>₹${w.revenue.toFixed(2)}</strong></td>
                            </tr>
                        `;
                    });
                }
            }
        })
        .catch(err => console.error("Error loading metrics:", err));
}

// 2. Manage Courts and Slots logic
function loadAdminCourts() {
    const select = document.getElementById('admin-court-select');
    const newSelect = document.getElementById('slot-new-court-select');
    const datePicker = document.getElementById('admin-date-select');
    if (!select) return;

    select.innerHTML = '';
    if (newSelect) newSelect.innerHTML = '';

    fetch('/api/courts')
        .then(res => res.json())
        .then(data => {
            if (data.success && data.courts.length > 0) {
                data.courts.forEach(court => {
                    select.innerHTML += `<option value="${court.id}">${court.name}</option>`;
                    if (newSelect) {
                        newSelect.innerHTML += `<option value="${court.id}">${court.name}</option>`;
                    }
                });
                
                // Set default date to TODAY (timezone aware) if empty
                if (!datePicker.value) {
                    const today = new Date();
                    const offset = today.getTimezoneOffset();
                    const localToday = new Date(today.getTime() - (offset * 60 * 1000));
                    datePicker.value = localToday.toISOString().split('T')[0];
                }
                
                // Trigger slots fetch
                loadAdminSlots();
            }
        })
        .catch(err => console.error("Error loading courts list:", err));
}

function loadAdminSlots() {
    const courtSelect = document.getElementById('admin-court-select');
    const dateSelect = document.getElementById('admin-date-select');
    const grid = document.getElementById('admin-slots-grid');

    if (!courtSelect || !dateSelect || !grid) return;

    const courtId = courtSelect.value;
    const dateStr = dateSelect.value;

    if (!courtId || !dateStr) return;

    grid.innerHTML = '<div class="slots-loading-spinner"><i class="fa-solid fa-spinner fa-spin"></i> Fetching slots...</div>';

    fetch(`/api/slots?date=${dateStr}&court_id=${courtId}`)
        .then(res => res.json())
        .then(data => {
            grid.innerHTML = '';
            if (data.success) {
                data.slots.forEach(slot => {
                    const card = document.createElement('div');
                    card.className = `slot-box status-${slot.status}`;
                    
                    let badge = 'Active';
                    if (slot.status === 'blocked') {
                        badge = slot.block_reason || 'Blocked';
                    } else if (slot.status === 'booked' || slot.status === 'booked_by_me') {
                        badge = 'Reserved';
                    } else if (slot.status === 'expired') {
                        badge = 'Expired';
                    }

                    const timeRangeFormatted = `${formatTimeTo12Hour(slot.start_time)} - ${formatTimeTo12Hour(slot.end_time)}`;

                    card.innerHTML = `
                        <span class="slot-box-time"><i class="fa-solid fa-clock"></i> ${timeRangeFormatted}</span>
                        <span class="slot-box-price">₹${slot.price}</span>
                        <span class="slot-box-status">${badge}</span>
                    `;

                    // Admin can click to edit any slot
                    card.onclick = () => {
                        openEditSlotModal(slot.slot_id, formatTimeTo12Hour(slot.start_time), formatTimeTo12Hour(slot.end_time), slot.price, slot.status === 'blocked', slot.block_reason);
                    };

                    grid.appendChild(card);
                });
            }
        })
        .catch(err => console.error("Error rendering admin slots grid:", err));
}

function createSlot(event) {
    event.preventDefault();
    const courtId = parseInt(document.getElementById('slot-new-court-select').value);
    const startInput = document.getElementById('slot-new-start');
    const endInput = document.getElementById('slot-new-end');
    const priceInput = document.getElementById('slot-new-price');

    const startTime24 = convert12HourTo24Hour(startInput.value);
    const endTime24 = convert12HourTo24Hour(endInput.value);

    if (!startTime24 || !endTime24) {
        window.showToast("Please enter valid 12-hour times (e.g., 06:00 AM, 11:30 PM).", "warning");
        return;
    }

    const payload = {
        court_id: courtId,
        start_time: startTime24,
        end_time: endTime24,
        default_price: parseFloat(priceInput.value)
    };

    fetch('/admin/api/slot', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            window.showToast(data.message, 'success');
            startInput.value = '';
            endInput.value = '';
            loadAdminSlots(); // Refresh current slots grid immediately!
        } else {
            window.showToast(data.message, 'error');
        }
    })
    .catch(err => console.error("Error creating slot:", err));
}

// Edit Slots overlay modal management
function openEditSlotModal(slotId, startTime, endTime, price, isBlocked, blockReason) {
    activeEditSlotId = slotId;
    const dateStr = document.getElementById('admin-date-select').value;

    document.getElementById('edit-slot-summary-time').innerText = `${startTime} - ${endTime}`;
    document.getElementById('edit-slot-summary-date').innerText = dateStr;
    document.getElementById('edit-slot-price').value = price;
    
    const blockSelect = document.getElementById('edit-slot-block-toggle');
    blockSelect.value = isBlocked ? "1" : "0";
    
    const reasonInput = document.getElementById('edit-slot-reason');
    reasonInput.value = blockReason || '';

    toggleBlockReasonInput();

    document.getElementById('modal-edit-slot').classList.remove('hidden');
}

function closeEditSlotModal() {
    document.getElementById('modal-edit-slot').classList.add('hidden');
    activeEditSlotId = null;
}

function toggleBlockReasonInput() {
    const val = document.getElementById('edit-slot-block-toggle').value;
    const reasonBox = document.getElementById('edit-slot-reason-box');
    if (val === "1") {
        reasonBox.classList.remove('hidden');
    } else {
        reasonBox.classList.add('hidden');
    }
}

function saveSlotConfiguration() {
    if (!activeEditSlotId) return;

    const dateStr = document.getElementById('admin-date-select').value;
    const priceVal = parseFloat(document.getElementById('edit-slot-price').value);
    const blockVal = parseInt(document.getElementById('edit-slot-block-toggle').value);
    const reasonVal = document.getElementById('edit-slot-reason').value;

    const pricingPayload = { slot_id: activeEditSlotId, date: dateStr, price: priceVal };
    const blockPayload = { slot_id: activeEditSlotId, date: dateStr, is_blocked: blockVal, reason: reasonVal };

    // Promise chain to update both pricing and blocking configurations
    Promise.all([
        fetch('/admin/api/slot/price', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(pricingPayload)
        }).then(res => res.json()),
        fetch('/admin/api/slot/block', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(blockPayload)
        }).then(res => res.json())
    ])
    .then(([priceRes, blockRes]) => {
        closeEditSlotModal();
        if (priceRes.success && blockRes.success) {
            window.showToast("Slot adjustments saved successfully!", 'success');
            loadAdminSlots();
        } else {
            window.showToast(priceRes.message || blockRes.message || "Failed to update slot settings.", 'error');
        }
    })
    .catch(err => {
        closeEditSlotModal();
        console.error("Save config error:", err);
        window.showToast("Error updating slot.", 'error');
    });
}

// 3. Live Booking Monitor Table
function loadBookingsLog() {
    const body = document.getElementById('bookings-log-body');
    body.innerHTML = '<tr><td colspan="8" class="text-center"><i class="fa-solid fa-spinner fa-spin"></i> Fetching logs...</td></tr>';

    fetch('/admin/api/bookings')
        .then(res => res.json())
        .then(data => {
            body.innerHTML = '';
            if (data.success) {
                if (data.bookings.length === 0) {
                    body.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No reservations found in the system database.</td></tr>';
                    return;
                }

                // Group bookings by date
                const groups = {};
                const datesOrder = [];
                data.bookings.forEach(b => {
                    if (!groups[b.date]) {
                        groups[b.date] = [];
                        datesOrder.push(b.date);
                    }
                    groups[b.date].push(b);
                });

                datesOrder.forEach(date => {
                    const bookingsForDate = groups[date];
                    bookingsForDate.sort((a, b) => {
                        const timeA = (a.time_range || '').replace("Daily ", "").split(" - ")[0];
                        const timeB = (b.time_range || '').replace("Daily ", "").split(" - ")[0];
                        const compareTime = timeA.localeCompare(timeB);
                        if (compareTime !== 0) return compareTime;
                        const courtA = a.court_name || '';
                        const courtB = b.court_name || '';
                        return courtA.localeCompare(courtB);
                    });
                    bookingsForDate.forEach((b, index) => {
                        let badgeClass = 'badge-confirmed';
                        let statusText = b.status.toUpperCase();
                        let action = '';

                        if (b.status === 'cancelled') {
                            badgeClass = 'badge-cancelled';
                        } else if (b.is_completed) {
                            badgeClass = 'badge-completed';
                            statusText = 'COMPLETED';
                        } else {
                            // Allow admin to cancel any confirmed active booking
                            action = `
                                <button class="btn-card-cancel" onclick="adminCancelBooking(${b.id})">
                                    <i class="fa-solid fa-ban"></i> Force Cancel
                                </button>
                            `;
                        }

                        // Render Date cell only once per group with rowspan
                        const dateCell = index === 0
                            ? `<td rowspan="${bookingsForDate.length}" class="booking-group-date-cell">
                                   <strong>${b.date}</strong>
                                   <div class="booking-group-count-badge">${bookingsForDate.length} ${bookingsForDate.length === 1 ? 'slot' : 'slots'}</div>
                               </td>`
                            : '';

                        const rowClass = index === 0 ? 'booking-group-first-row' : '';

                        let timeRangeText = formatTimeTo12Hour(b.time_range);
                        let membersText = `${b.members} Players`;
                        if (b.id >= 1000000) {
                            let rawTime = b.time_range.replace("Daily ", "");
                            timeRangeText = `Daily ${formatTimeTo12Hour(rawTime)}`;
                            membersText = `${b.members}`;
                        }

                        // Escape single quotes for parameter safety
                        const escName = (b.user_name || '').replace(/'/g, "\\'");
                        const escEmail = (b.user_email || '').replace(/'/g, "\\'");
                        const escMobile = (b.user_mobile || '').replace(/'/g, "\\'");
                        const escCourt = (b.court_name || '').replace(/'/g, "\\'");

                        let agreementButton = '';
                        if (b.id >= 1000000 && b.status === 'confirmed') {
                            const membershipId = b.id - 1000000;
                            const duration = b.members.replace(' Plan', '');
                            agreementButton = `
                                <button class="btn-table-download" onclick="downloadMembershipAgreement(event, '${membershipId}', '${b.date}', '${b.time_range.replace('Daily ', '')}', '${duration}', ${b.price}, '${escCourt}', '${b.created_at}', '${escName}', '${escEmail}', '${escMobile}')">
                                    <i class="fa-solid fa-file-arrow-down"></i> Agreement
                                </button>
                            `;
                        }

                        body.innerHTML += `
                            <tr class="${rowClass}">
                                ${dateCell}
                                <td>
                                    <div><strong>${b.user_name}</strong></div>
                                    <div class="query-user-details">${b.user_mobile || '—'}</div>
                                </td>
                                <td>${b.court_name}</td>
                                <td><i class="fa-regular fa-clock"></i> ${timeRangeText}</td>
                                <td>${membersText}</td>
                                <td class="text-accent"><strong>₹${b.price.toFixed(2)}</strong></td>
                                <td>
                                    <div class="status-cell-container">
                                        <span class="history-status-badge ${badgeClass}">${statusText}</span>
                                        ${agreementButton}
                                    </div>
                                </td>
                                <td>${action}</td>
                            </tr>
                        `;
                    });
                });
            }
        })
        .catch(err => console.error(err));
}

function adminCancelBooking(bookingId) {
    if (!confirm("Are you sure you want to FORCE CANCEL this session as administrator?")) return;

    fetch('/api/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ booking_id: bookingId })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            window.showToast("Reservation force cancelled.", 'success');
            loadBookingsLog();
        } else {
            window.showToast(data.message, 'error');
        }
    })
    .catch(err => console.error(err));
}

// 4. Customer Support Queries replies
function loadCustomerQueries() {
    const container = document.getElementById('admin-queries-list');
    container.innerHTML = '<div class="slots-loading-spinner"><i class="fa-solid fa-spinner fa-spin"></i> Loading user tickets...</div>';

    fetch('/admin/api/queries')
        .then(res => res.json())
        .then(data => {
            container.innerHTML = '';
            if (data.success) {
                if (data.queries.length === 0) {
                    container.innerHTML = '<div class="dashboard-empty-state"><i class="fa-solid fa-check-double text-accent"></i><p>All clean! No query tickets raised.</p></div>';
                    return;
                }

                data.queries.forEach(q => {
                    const card = document.createElement('div');
                    card.className = `ticket-card glass-card status-${q.status}`;
                    
                    let replyBlock = '';
                    if (q.status === 'pending') {
                        replyBlock = `
                            <button class="btn-admin-reply" onclick="openReplyModal(${q.id}, '${q.user_name}', '${q.subject}', '${q.message}')">
                                <i class="fa-solid fa-reply"></i> Compose Reply
                            </button>
                        `;
                    } else {
                        replyBlock = `
                            <div class="ticket-reply-bubble">
                                <strong>Your Response:</strong>
                                <p>${q.reply}</p>
                            </div>
                        `;
                    }

                    card.innerHTML = `
                        <div class="ticket-header">
                            <span class="ticket-subject">Subject: ${q.subject}</span>
                            <span class="ticket-status-badge badge-${q.status}">${q.status.toUpperCase()}</span>
                        </div>
                        <div class="query-user-details">
                            Raised by: <strong>${q.user_name}</strong> (${q.user_email}) | ${new Date(q.created_at).toLocaleString()}
                        </div>
                        <div class="ticket-message">
                            <p class="user-msg">"${q.message}"</p>
                        </div>
                        ${replyBlock}
                    `;
                    container.appendChild(card);
                });
            }
        })
        .catch(err => console.error(err));
}

function updateQueryBadgeCount() {
    fetch('/admin/api/queries')
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                const pendingCount = data.queries.filter(q => q.status === 'pending').length;
                const badge = document.getElementById('queries-badge-count');
                if (badge) {
                    if (pendingCount > 0) {
                        badge.innerText = pendingCount;
                        badge.classList.remove('hidden');
                    } else {
                        badge.classList.add('hidden');
                    }
                }
            }
        })
        .catch(err => console.error(err));
}

function openReplyModal(queryId, userName, subject, message) {
    activeReplyQueryId = queryId;
    document.getElementById('reply-modal-username').innerText = userName;
    document.getElementById('reply-modal-subject').innerText = subject;
    document.getElementById('reply-modal-complaint').innerText = `"${message}"`;
    document.getElementById('reply-modal-message').value = '';

    document.getElementById('modal-reply-query').classList.remove('hidden');
}

function closeReplyModal() {
    document.getElementById('modal-reply-query').classList.add('hidden');
    activeReplyQueryId = null;
}

function submitQueryReply() {
    if (!activeReplyQueryId) return;

    const replyMsg = document.getElementById('reply-modal-message').value.strip ? document.getElementById('reply-modal-message').value.strip() : document.getElementById('reply-modal-message').value.trim();
    if (!replyMsg) {
        window.showToast("Reply message cannot be blank.", 'warning');
        return;
    }

    const payload = {
        query_id: activeReplyQueryId,
        reply: replyMsg
    };

    fetch('/admin/api/query/reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        closeReplyModal();
        if (data.success) {
            window.showToast(data.message, 'success');
            loadCustomerQueries();
            updateQueryBadgeCount();
        } else {
            window.showToast(data.message, 'error');
        }
    })
    .catch(err => {
        closeReplyModal();
        console.error(err);
        window.showToast("Submit reply failed.", 'error');
    });
}

// 5. Manage Memberships tracking
function loadMembershipsLog() {
    const body = document.getElementById('memberships-log-body');
    if (!body) return;
    body.innerHTML = '<tr><td colspan="8" class="text-center"><i class="fa-solid fa-spinner fa-spin"></i> Fetching subscriptions...</td></tr>';

    fetch('/admin/api/memberships')
        .then(res => res.json())
        .then(data => {
            body.innerHTML = '';
            if (data.success) {
                if (data.memberships.length === 0) {
                    body.innerHTML = '<tr><td colspan="8" class="text-center text-muted">No memberships registered.</td></tr>';
                    return;
                }

                data.memberships.forEach(m => {
                    let badgeClass = 'badge-confirmed';
                    let statusText = m.status.toUpperCase();
                    let action = '';

                    if (m.status === 'cancelled') {
                        badgeClass = 'badge-cancelled';
                    } else if (m.is_completed) {
                        badgeClass = 'badge-completed';
                        statusText = 'COMPLETED';
                    } else {
                        // Allow admin to force cancel active membership
                        action = `
                            <button class="btn-card-cancel" onclick="adminCancelMembership(${m.id})">
                                <i class="fa-solid fa-ban"></i> Force Cancel
                            </button>
                        `;
                    }

                    // Escape single quotes to prevent breaking the onclick string parameter
                    const escName = (m.user_name || '').replace(/'/g, "\\'");
                    const escEmail = (m.user_email || '').replace(/'/g, "\\'");
                    const escMobile = (m.user_mobile || '').replace(/'/g, "\\'");
                    const escCourt = (m.court_name || '').replace(/'/g, "\\'");

                    let agreementButton = '';
                    if (m.status === 'confirmed') {
                        agreementButton = `
                            <button class="btn-table-download" onclick="downloadMembershipAgreement(event, '${m.id}', '${m.start_date} to ${m.end_date}', '${m.time_range}', '${m.duration}', ${m.amount}, '${escCourt}', '${m.created_at}', '${escName}', '${escEmail}', '${escMobile}')">
                                <i class="fa-solid fa-file-arrow-down"></i> Agreement
                            </button>
                        `;
                    }

                    const bookedDate = m.created_at ? m.created_at.split(' ')[0] : '—';
                    body.innerHTML += `
                        <tr>
                            <td>
                                <div><strong>${m.start_date}</strong> to <strong>${m.end_date}</strong></div>
                                <div class="query-user-details" style="margin-top: 4px;"><i class="fa-solid fa-clock-rotate-left" style="font-size: 10px;"></i> Booked: ${bookedDate}</div>
                            </td>
                            <td>
                                <div><strong>${m.user_name}</strong></div>
                                <div class="query-user-details">${m.user_mobile || '—'}</div>
                            </td>
                            <td>${m.court_name}</td>
                            <td><i class="fa-regular fa-clock"></i> ${formatTimeTo12Hour(m.time_range)}</td>
                            <td>${m.duration}</td>
                            <td class="text-accent"><strong>₹${m.amount.toFixed(2)}</strong></td>
                            <td>
                                <div class="status-cell-container">
                                    <span class="history-status-badge ${badgeClass}">${statusText}</span>
                                    ${agreementButton}
                                </div>
                            </td>
                            <td>${action}</td>
                        </tr>
                    `;
                });
            } else {
                body.innerHTML = `<tr><td colspan="8" class="text-center text-error">${data.message || 'Failed to load.'}</td></tr>`;
            }
        })
        .catch(err => {
            console.error(err);
            body.innerHTML = '<tr><td colspan="8" class="text-center text-error">Failed to connect to API.</td></tr>';
        });
}

function adminCancelMembership(membershipId) {
    if (!confirm("Are you sure you want to FORCE CANCEL this membership subscription as administrator? All blocked days will immediately become available.")) return;

    fetch('/api/cancel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ booking_id: 1000000 + membershipId }) // Use offset
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            window.showToast("Membership subscription force cancelled.", 'success');
            loadMembershipsLog();
        } else {
            window.showToast(data.message, 'error');
        }
    })
    .catch(err => console.error(err));
}

// Canvas agreement generation function
function downloadAgreementImage(details) {
    const canvas = document.createElement('canvas');
    canvas.width = 1200;
    canvas.height = 850;
    const ctx = canvas.getContext('2d');
    
    // Background Gradient
    const grad = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
    grad.addColorStop(0, '#0a1128');
    grad.addColorStop(0.5, '#102a43');
    grad.addColorStop(1, '#072236');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Inner Glassmorphism Panel
    ctx.fillStyle = 'rgba(255, 255, 255, 0.02)';
    ctx.beginPath();
    if (ctx.roundRect) {
        ctx.roundRect(40, 40, canvas.width - 80, canvas.height - 80, 20);
    } else {
        ctx.rect(40, 40, canvas.width - 80, canvas.height - 80);
    }
    ctx.fill();
    
    // Emerald Border
    ctx.strokeStyle = '#10B981';
    ctx.lineWidth = 4;
    ctx.beginPath();
    if (ctx.roundRect) {
        ctx.roundRect(45, 45, canvas.width - 90, canvas.height - 90, 18);
    } else {
        ctx.rect(45, 45, canvas.width - 90, canvas.height - 90);
    }
    ctx.stroke();
    
    // Gold Border
    ctx.strokeStyle = '#FBBF24';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    if (ctx.roundRect) {
        ctx.roundRect(55, 55, canvas.width - 110, canvas.height - 110, 15);
    } else {
        ctx.rect(55, 55, canvas.width - 110, canvas.height - 110);
    }
    ctx.stroke();
    
    // Shield Decoration
    ctx.shadowColor = 'rgba(16, 185, 129, 0.4)';
    ctx.shadowBlur = 15;
    ctx.fillStyle = '#10B981';
    ctx.beginPath();
    ctx.moveTo(600, 90);
    ctx.lineTo(630, 120);
    ctx.lineTo(600, 150);
    ctx.lineTo(570, 120);
    ctx.closePath();
    ctx.fill();
    
    // Gold Star Inside Shield
    ctx.fillStyle = '#FBBF24';
    ctx.beginPath();
    ctx.moveTo(600, 105);
    ctx.lineTo(610, 120);
    ctx.lineTo(600, 135);
    ctx.lineTo(590, 120);
    ctx.closePath();
    ctx.fill();
    
    ctx.shadowBlur = 0;
    
    // Header Text
    ctx.textAlign = 'center';
    ctx.fillStyle = '#FFFFFF';
    ctx.font = '800 32px "Outfit", sans-serif';
    ctx.fillText('TRISTAR BADMINTON ACADEMY', 600, 205);
    
    ctx.fillStyle = '#10B981';
    ctx.font = '600 16px "Outfit", sans-serif';
    ctx.fillText('OFFICIAL MEMBERSHIP SUBSCRIPTION AGREEMENT', 600, 235);
    
    // Divider line
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(200, 260);
    ctx.lineTo(1000, 260);
    ctx.stroke();
    
    // Description
    ctx.fillStyle = '#E2E8F0';
    ctx.font = 'italic 15px "Plus Jakarta Sans", sans-serif';
    ctx.fillText('This agreement certifies that the slot reservation is locked and confirmed for the period listed below.', 600, 295);
    
    // Detail drawer helper
    function drawDetailItem(x, y, label, value, valColor = '#FFFFFF') {
        ctx.textAlign = 'left';
        ctx.fillStyle = '#94A3B8';
        ctx.font = '600 13px "Outfit", sans-serif';
        ctx.fillText(label.toUpperCase(), x, y);
        
        ctx.fillStyle = valColor;
        ctx.font = 'bold 18px "Plus Jakarta Sans", sans-serif';
        ctx.fillText(value, x, y + 25);
    }
    
    // Left Column (Member Info)
    let currentY = 360;
    const startXLeft = 130;
    drawDetailItem(startXLeft, currentY, 'Member Name', details.name || 'Anonymous User');
    currentY += 65;
    drawDetailItem(startXLeft, currentY, 'Registered Email', details.email || '—');
    currentY += 65;
    drawDetailItem(startXLeft, currentY, 'Mobile Number', details.mobile || '—');
    currentY += 65;
    drawDetailItem(startXLeft, currentY, 'Agreement ID', `TBA-MEM-${details.membership_id.toString().padStart(5, '0')}`, '#FBBF24');
    
    // Right Column (Subscription Info)
    currentY = 360;
    const startXRight = 630;
    drawDetailItem(startXRight, currentY, 'Reserved Court Name', details.court_name);
    currentY += 65;
    drawDetailItem(startXRight, currentY, 'Daily Time Slot', details.time_range);
    currentY += 65;
    drawDetailItem(startXRight, currentY, 'Validity Period', `${details.start_date} to ${details.end_date}`, '#10B981');
    currentY += 65;
    drawDetailItem(startXRight, currentY, 'Duration & Amount Paid', `${details.duration} Plan  |  ₹${parseFloat(details.amount).toLocaleString('en-IN')}.00 (FULLY PAID)`, '#34D399');
    
    // Divider
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
    ctx.beginPath();
    ctx.moveTo(130, 640);
    ctx.lineTo(1070, 640);
    ctx.stroke();
    
    // Circular Seal
    ctx.shadowColor = 'rgba(251, 191, 36, 0.3)';
    ctx.shadowBlur = 10;
    ctx.strokeStyle = '#FBBF24';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(220, 725, 45, 0, Math.PI * 2);
    ctx.stroke();
    
    ctx.fillStyle = '#FBBF24';
    ctx.font = 'bold 10px "Outfit", sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('TRISTAR', 220, 715);
    ctx.font = '800 11px "Outfit", sans-serif';
    ctx.fillText('APPROVED', 220, 730);
    ctx.font = 'bold 9px "Outfit", sans-serif';
    ctx.fillText('SEAL', 220, 743);
    ctx.shadowBlur = 0;
    
    // Signatures
    ctx.textAlign = 'right';
    ctx.fillStyle = '#E2E8F0';
    ctx.font = 'italic 16px "Plus Jakarta Sans", sans-serif';
    ctx.fillText('Tristar Academy Executive Board', 1070, 715);
    
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(850, 730);
    ctx.lineTo(1070, 730);
    ctx.stroke();
    
    ctx.fillStyle = '#94A3B8';
    ctx.font = '600 11px "Outfit", sans-serif';
    ctx.fillText('AUTHORIZED SIGNATURE', 1070, 750);
    
    // Date of Issue
    ctx.textAlign = 'center';
    ctx.fillStyle = '#64748B';
    ctx.font = '600 11px "Outfit", sans-serif';
    const issueDate = details.created_at ? new Date(details.created_at.replace ? details.created_at.replace(' ', 'T') : details.created_at).toLocaleDateString('en-IN', {year:'numeric', month:'long', day:'numeric'}) : new Date().toLocaleDateString('en-IN', {year:'numeric', month:'long', day:'numeric'});
    ctx.fillText(`AGREEMENT ISSUED ON: ${issueDate}`, 600, 790);
    
    // Download anchor trigger
    const dataUrl = canvas.toDataURL('image/png');
    const link = document.createElement('a');
    link.download = `Tristar_Membership_Agreement_${details.membership_id}.png`;
    link.href = dataUrl;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Helper to download membership agreement from admin table parameters
function downloadMembershipAgreement(event, membershipId, dateRange, timeSlot, duration, amount, courtName, createdAt, userName, userEmail, userMobile) {
    if (event) event.preventDefault();
    
    const dates = dateRange.split(' to ');
    const startDate = dates[0];
    const endDate = dates[1];
    
    const timeRange = formatTimeTo12Hour(timeSlot);
    
    const details = {
        name: userName,
        email: userEmail,
        mobile: userMobile,
        court_name: courtName,
        time_range: timeRange,
        start_date: startDate,
        end_date: endDate,
        duration: duration,
        amount: amount,
        created_at: createdAt,
        membership_id: membershipId
    };
    
    downloadAgreementImage(details);
}
