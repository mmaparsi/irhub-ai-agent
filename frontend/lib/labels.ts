export const roleLabel: Record<string, string> = {
  admin: "مدیر",
  expert: "کارشناس",
  viewer: "بیننده",
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
