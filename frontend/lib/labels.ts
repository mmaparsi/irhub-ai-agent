export const roleLabel: Record<string, string> = {
  admin: "مدیرکل سیستم",
  sales: "کارشناس فروش",
  supplier_acquisition: "کارشناس جذب تامین‌کننده",
  expert: "کارشناس",
  viewer: "بیننده",
};

export const partyLabel: Record<string, string> = {
  customer: "مشتری",
  supplier: "تأمین‌کننده",
};

export const channelLabel: Record<string, string> = {
  panel: "پنل",
  email: "ایمیل",
  telegram: "تلگرام",
  whatsapp: "واتساپ",
  sms: "پیامک",
};

export const taskStatus: Record<string, string> = {
  queued: "در صف",
  running: "در حال اجرا",
  waiting_approval: "منتظر تأیید",
  stopping: "در حال توقف",
  completed: "تمام شد",
  failed: "ناموفق",
  stopped: "متوقف",
};

export const leadStatus: Record<string, string> = {
  new: "جدید",
  qualified: "واجد شرایط",
  negotiating: "در مذاکره",
  won: "موفق",
  lost: "از دست‌رفته",
};

export const approvalStatus: Record<string, string> = {
  pending: "در انتظار",
  approved: "تأیید شده",
  rejected: "رد شده",
};

export const executionStatus: Record<string, string> = {
  not_started: "شروع نشده",
  queued: "در صف اجرا",
  executed: "اجرای آزمایشی انجام شد",
  failed: "ناموفق",
  skipped: "اجرا نشد",
};

export const actionLabel: Record<string, string> = {
  email: "ایمیل",
  message: "پیام",
  price_offer: "پیشنهاد قیمت",
};
