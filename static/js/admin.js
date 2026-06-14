// Academy Admin Dashboard Controller logic
let activeEditSlotId = null;
let activeReplyQueryId = null;
let loadedQueries = [];
let loadedBookingsLog = [];

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
                loadedBookingsLog = data.bookings;
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
                            action = b.cancelled_at ? `<span style="color: var(--color-error); font-size: 12px; font-weight: 600; line-height: 1.3; display: inline-block;"><i class="fa-solid fa-clock-rotate-left"></i> Cancelled:<br>${b.cancelled_at}</span>` : '—';
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
                        } else if (b.id < 1000000 && b.status === 'confirmed') {
                            const isExpired = window.isSlotHourPassed ? window.isSlotHourPassed(b.date, b.time_range) : false;
                            if (!isExpired) {
                                agreementButton = `
                                    <button class="btn-table-download" onclick="downloadHourlyReceipt(event, '${b.id}', '${b.date}', '${b.time_range}', ${b.members}, ${b.price}, '${escCourt}', '${b.created_at}', '${escName}', '${escEmail}', '${escMobile}', '${b.payment_method}')">
                                        <i class="fa-solid fa-file-arrow-down"></i> Receipt
                                    </button>
                                `;
                            } else {
                                agreementButton = `
                                    <button class="btn-table-download disabled" style="opacity: 0.5; cursor: not-allowed;" disabled title="Download expired after slot hour">
                                        <i class="fa-solid fa-file-arrow-down"></i> Receipt
                                    </button>
                                `;
                            }
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
                                <td class="text-accent">
                                    <strong>₹${b.price.toFixed(2)}</strong>
                                    <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px; text-transform: capitalize; font-weight: 500;">
                                        <i class="${b.payment_method === 'offline' ? 'fa-solid fa-handshake text-accent' : 'fa-solid fa-qrcode text-accent'}"></i> ${b.payment_method === 'offline' ? 'Offline' : 'Online (UPI)'}
                                    </div>
                                </td>
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

function exportBookingsToExcel() {
    if (!loadedBookingsLog || loadedBookingsLog.length === 0) {
        window.showToast("No bookings to export.", "warning");
        return;
    }
    
    // Prepare Excel headers
    const headers = ["Booking ID", "Date", "User Name", "Mobile", "Email", "Court Name", "Time Slot", "Players/Members", "Price (INR)", "Payment Method", "Status", "Created At", "Cancelled At"];
    
    // Format rows
    const rows = loadedBookingsLog.map(b => [
        b.id,
        b.date,
        b.user_name,
        b.user_mobile || "—",
        b.user_email || "—",
        b.court_name,
        b.time_range,
        b.members,
        b.price,
        b.payment_method === 'offline' ? 'Offline' : 'Online (UPI)',
        b.status.toUpperCase(),
        b.created_at,
        b.cancelled_at || "—"
    ]);
    
    try {
        // Create workbook and worksheet
        const wb = XLSX.utils.book_new();
        const ws = XLSX.utils.aoa_to_sheet([headers, ...rows]);
        
        // Auto-fit column widths to ensure dates and mobile numbers are fully visible
        const colWidths = headers.map((h, i) => {
            let maxLen = h.length;
            rows.forEach(row => {
                const val = (row[i] !== undefined && row[i] !== null) ? String(row[i]) : '';
                if (val.length > maxLen) {
                    maxLen = val.length;
                }
            });
            return { wch: maxLen + 3 }; // Add safety padding
        });
        ws['!cols'] = colWidths;
        
        // Append worksheet to workbook
        XLSX.utils.book_append_sheet(wb, ws, "Bookings History");
        
        // Write XLSX file using binary array Blob for high compatibility on mobile and desktop
        const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
        const blob = new Blob([wbout], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
        const filename = `Tristar_Badminton_Bookings_Export_${new Date().toISOString().split('T')[0]}.xlsx`;
        
        const blobUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = blobUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(() => URL.revokeObjectURL(blobUrl), 100);
    } catch (err) {
        console.error("SheetJS export failed:", err);
        window.showToast("Failed to export Excel file.", "error");
    }
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
                loadedQueries = data.queries;
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
                            <button class="btn-admin-reply" onclick="openReplyModal(${q.id})">
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

function openReplyModal(queryId) {
    const q = loadedQueries.find(item => item.id === queryId);
    if (!q) return;
    activeReplyQueryId = queryId;
    document.getElementById('reply-modal-username').innerText = q.user_name;
    document.getElementById('reply-modal-subject').innerText = q.subject;
    document.getElementById('reply-modal-complaint').innerText = `"${q.message}"`;
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
                        action = m.cancelled_at ? `<span style="color: var(--color-error); font-size: 12px; font-weight: 600; line-height: 1.3; display: inline-block;"><i class="fa-solid fa-clock-rotate-left"></i> Cancelled:<br>${m.cancelled_at}</span>` : '—';
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
    
    window.downloadAgreementImage(details);
}

function downloadHourlyReceipt(event, bookingId, date, timeSlot, members, price, courtName, createdAt, userName, userEmail, userMobile, paymentMethod) {
    if (event) event.preventDefault();
    
    const details = {
        name: userName,
        email: userEmail,
        mobile: userMobile,
        court_name: courtName,
        time_range: formatTimeTo12Hour(timeSlot),
        date: date,
        num_members: members,
        amount: price,
        created_at: createdAt,
        booking_id: bookingId,
        payment_method: paymentMethod
    };
    
    window.downloadReceiptImage(details);
}
