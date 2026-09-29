/**
 * Орион — мост към Google (Gmail, Календар, Задачи).
 *
 * Работи в собствения ви Google акаунт като уеб приложение. Орион му изпраща заявки с таен
 * ключ; без ключа мостът не връща нищо. Инструкции: README.md -> „Връзка с Google“.
 */
var SECRET = '__ORION_SECRET__';

function doGet() {
  return ContentService.createTextOutput('Мостът на Орион работи. Поставете адреса на тази страница в Орион.');
}

function doPost(e) {
  var request;
  try {
    request = JSON.parse(e.postData.contents);
  } catch (err) {
    return reply_({ error: 'невалидна заявка' });
  }
  if (!request || request.secret !== SECRET) return reply_({ error: 'грешен ключ' });
  var action = ACTIONS[request.action];
  if (!action) return reply_({ error: 'непознато действие: ' + request.action });
  try {
    return reply_({ result: action(request.params || {}) });
  } catch (err) {
    return reply_({ error: String((err && err.message) || err) });
  }
}

function reply_(data) {
  return ContentService.createTextOutput(JSON.stringify(data)).setMimeType(ContentService.MimeType.JSON);
}

// Дати без час („2026-09-26“) — в часовата зона на скрипта, за да не се измести денят.
function localDate_(text) {
  var p = String(text).split('-');
  return new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
}

function dayText_(date) {
  return Utilities.formatDate(date, Session.getScriptTimeZone(), 'yyyy-MM-dd');
}

var ACTIONS = {
  ping: function () {
    return { email: Session.getEffectiveUser().getEmail(), calendar: CalendarApp.getDefaultCalendar().getName() };
  },

  // --- Календар ---------------------------------------------------------------------------
  calendar_list: function (p) {
    var events = CalendarApp.getDefaultCalendar().getEvents(new Date(p.start), new Date(p.end));
    return events.slice(0, 30).map(function (ev) {
      var allDay = ev.isAllDayEvent();
      return {
        id: ev.getId(), title: ev.getTitle(), location: ev.getLocation(), allDay: allDay,
        start: allDay ? dayText_(ev.getAllDayStartDate()) : ev.getStartTime().toISOString(),
        end: allDay ? dayText_(ev.getAllDayEndDate()) : ev.getEndTime().toISOString()
      };
    });
  },

  calendar_create: function (p) {
    var calendar = CalendarApp.getDefaultCalendar();
    var options = { location: p.location || '', description: p.description || '' };
    var ev = p.allDay
      ? calendar.createAllDayEvent(p.title, localDate_(p.date), options)
      : calendar.createEvent(p.title, new Date(p.start), new Date(p.end), options);
    return { id: ev.getId(), title: ev.getTitle() };
  },

  calendar_delete: function (p) {
    var ev = CalendarApp.getDefaultCalendar().getEventById(p.id);
    if (!ev) throw new Error('събитието вече не съществува');
    ev.deleteEvent();
    return { deleted: true };
  },

  // --- Поща ------------------------------------------------------------------------------
  mail_list: function (p) {
    var threads = GmailApp.search(p.query || 'in:inbox is:unread -category:promotions -category:social', 0, p.max || 5);
    return threads.map(function (thread) {
      var messages = thread.getMessages();
      var m = messages[messages.length - 1];
      return {
        id: m.getId(), from: m.getFrom(), subject: m.getSubject(), date: m.getDate().toISOString(),
        unread: m.isUnread(), snippet: m.getPlainBody().replace(/\s+/g, ' ').slice(0, 200)
      };
    });
  },

  mail_read: function (p) {
    var m = GmailApp.getMessageById(p.id);
    if (!m) throw new Error('писмото не е намерено');
    m.markRead();
    return {
      from: m.getFrom(), to: m.getTo(), subject: m.getSubject(), date: m.getDate().toISOString(),
      body: m.getPlainBody().slice(0, p.maxChars || 3000)
    };
  },

  mail_send: function (p) {
    if (p.replyToId) {
      GmailApp.getMessageById(p.replyToId).reply(p.body);
    } else {
      GmailApp.sendEmail(p.to, p.subject, p.body);
    }
    return { sent: true };
  },

  // Адрес по име: търси го в писмата, които сте получавали или пращали.
  contact_find: function (p) {
    var me = Session.getEffectiveUser().getEmail().toLowerCase();
    var found = {};
    (p.names || []).forEach(function (name) {
      var needle = String(name).toLowerCase();
      GmailApp.search('from:(' + name + ') OR to:(' + name + ')', 0, 20).forEach(function (thread) {
        thread.getMessages().forEach(function (m) {
          [m.getFrom(), m.getTo(), m.getCc()].join(',').split(',').forEach(function (entry) {
            var match = entry.match(/^\s*"?([^"<]*?)"?\s*<([^>]+)>/) || entry.match(/()([^\s<>",]+@[^\s<>",]+)/);
            if (!match) return;
            var email = match[2].trim().toLowerCase();
            var display = match[1].trim();
            if (email === me) return;
            if (display.toLowerCase().indexOf(needle) < 0 && email.indexOf(needle) < 0) return;
            found[email] = found[email] || { name: display, email: email, count: 0 };
            found[email].count += 1;
          });
        });
      });
    });
    return Object.keys(found).map(function (k) { return found[k]; })
      .sort(function (a, b) { return b.count - a.count; }).slice(0, 5);
  },

  // --- Задачи (изисква услугата „Google Tasks API“ в скрипта) ------------------------------
  tasks_list: function () {
    var result = Tasks.Tasks.list('@default', { showCompleted: false, maxResults: 50 });
    return (result.items || []).map(function (t) {
      return { id: t.id, title: t.title, due: t.due ? t.due.slice(0, 10) : '', notes: t.notes || '' };
    });
  },

  tasks_add: function (p) {
    var task = { title: p.title, notes: p.notes || '' };
    if (p.due) task.due = p.due + 'T00:00:00.000Z';
    var created = Tasks.Tasks.insert(task, '@default');
    return { id: created.id, title: created.title };
  },

  tasks_complete: function (p) {
    Tasks.Tasks.patch({ status: 'completed' }, '@default', p.id);
    return { completed: true };
  }
};
