import { useState, useEffect } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useLang } from "@/contexts/LanguageContext";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Languages, ShieldCheck, KeyRound, Mail } from "lucide-react";

export default function Login() {
  const { login, verifyOtp, resendOtp, acceptInvite } = useAuth();
  const { lang, toggle: toggleLang, t } = useLang();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const inviteToken = params.get("invite");
  const inviteEmail = params.get("email");

  const [stage, setStage] = useState(inviteToken ? "invite" : "credentials"); // credentials | otp | invite
  const [email, setEmail] = useState(inviteEmail || "");
  const [password, setPassword] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [otpId, setOtpId] = useState(null);
  const [tempPassword, setTempPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [emailSent, setEmailSent] = useState(false);

  useEffect(() => {
    if (inviteToken && inviteEmail) {
      setStage("invite");
      setEmail(inviteEmail);
    }
  }, [inviteToken, inviteEmail]);

  const submitCredentials = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await login(email, password);
      if (res.otpRequired) {
        setOtpId(res.otpId);
        setEmailSent(res.emailSent);
        setStage("otp");
        if (res.emailSent) {
          toast.success(t("أرسلنا رمز الدخول إلى بريدك", "Sign-in code sent to your email"));
        } else {
          toast.message(t("الإيميل غير مهيأ — راجع المسؤول", "Email not configured — contact admin"));
        }
      } else {
        toast.success(t("مرحبًا بعودتك", "Welcome back"));
        navigate("/");
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("فشل تسجيل الدخول", "Sign-in failed"));
    } finally {
      setLoading(false);
    }
  };

  const submitOtp = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await verifyOtp(otpId, otpCode.trim());
      toast.success(t("تم الدخول", "Signed in"));
      navigate("/");
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("رمز خاطئ", "Wrong code"));
    } finally {
      setLoading(false);
    }
  };

  const resend = async () => {
    setLoading(true);
    try {
      const r = await resendOtp(otpId);
      if (r.ok) toast.success(t("أعدنا إرسال الرمز", "Code resent"));
      else toast.error(r.detail || t("فشل إعادة الإرسال", "Resend failed"));
    } catch (err) {
      toast.error(t("فشل", "Failed"));
    } finally {
      setLoading(false);
    }
  };

  const submitInvite = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const r = await acceptInvite(inviteToken, tempPassword);
      toast.success(t("تم قبول الدعوة", "Invite accepted"));
      if (r.mustChangePassword) {
        navigate("/settings?force=password");
      } else {
        navigate("/");
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("رمز خاطئ", "Wrong code"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex bg-background text-foreground">
      <div className="hidden md:flex flex-1 relative border-e border-border noise">
        <div className="absolute inset-0 grid-bg opacity-30" />
        <div className="relative z-10 p-12 flex flex-col justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-primary flex items-center justify-center rounded-sm">
              <span className="text-primary-foreground font-mono font-bold text-sm">O</span>
            </div>
            <span className="font-medium tracking-tight">{t("أوبس‌كور", "OpsCore")}</span>
          </div>
          <div className="space-y-6">
            <div className="label-mono">{t("نظام تشغيل ذكي للمؤسسين", "Smart OS for founders")}</div>
            <h1 className="text-4xl sm:text-5xl tracking-tight font-medium leading-[1.2] max-w-md">
              {t("أدِر يومك كأنّ لديك رئيس عمليات.", "Run your day like you have a Chief of Operations.")}
            </h1>
            <p className="text-muted-foreground max-w-sm leading-relaxed">
              {t(
                "دخول آمن بخطوتين، جلسات قصيرة، وصلاحيات دقيقة لكل مشروع.",
                "Two-step sign-in, short sessions, fine-grained per-project access."
              )}
            </p>
            <div className="grid grid-cols-3 gap-px bg-border max-w-md">
              {[
                { l: t("جلسة", "Session"), v: t("٦ ساعات", "6h") },
                { l: t("OTP", "OTP"), v: t("بريد", "Email") },
                { l: t("الوكيل", "Agent"), v: t("كلود ٤٫٥", "Claude 4.5") },
              ].map((s) => (
                <div key={s.l} className="bg-background p-4">
                  <div className="label-mono text-[10px]">{s.l}</div>
                  <div className="data-number text-2xl mt-1">{s.v}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="label-mono">{t("الإصدار ١٫١ · للمؤسسين", "v1.1 · for founders")}</div>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-8 relative">
        <button
          type="button"
          data-testid="lang-toggle-btn"
          onClick={toggleLang}
          className="absolute top-6 end-6 h-9 px-3 flex items-center gap-1.5 rounded-md border border-border hover:bg-secondary transition-colors text-xs font-mono"
          aria-label="Toggle language"
        >
          <Languages size={14} />
          <span className="uppercase">{lang === "ar" ? "EN" : "AR"}</span>
        </button>

        {stage === "credentials" && (
          <form onSubmit={submitCredentials} className="w-full max-w-sm space-y-6" data-testid="login-form">
            <div>
              <div className="label-mono">{t("تسجيل الدخول", "Sign in")}</div>
              <h2 className="text-2xl tracking-tight font-medium mt-1">{t("ادخل النظام", "Enter the system")}</h2>
            </div>
            <div className="space-y-3">
              <div>
                <label className="label-mono mb-1.5 block">{t("البريد الإلكتروني", "Email")}</label>
                <input
                  data-testid="login-email"
                  type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                  dir="ltr"
                  className="w-full px-3 py-2.5 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary text-left"
                  placeholder="you@founder.so"
                />
              </div>
              <div>
                <label className="label-mono mb-1.5 block">{t("كلمة المرور", "Password")}</label>
                <input
                  data-testid="login-password"
                  type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                  dir="ltr"
                  className="w-full px-3 py-2.5 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary text-left"
                  placeholder="••••••••"
                />
              </div>
            </div>
            <button
              data-testid="login-submit"
              type="submit" disabled={loading}
              className="w-full bg-primary text-primary-foreground py-2.5 rounded-md font-medium text-sm hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? t("جارٍ تسجيل الدخول…", "Signing in…") : <>{t("متابعة", "Continue")} <ArrowLeft size={14} className="rtl:rotate-180" /></>}
            </button>
            <p className="label-mono text-[10px] text-muted-foreground text-center">
              {t("الوصول بالدعوة فقط — تواصل مع المالك للانضمام", "Access by invite only — contact the owner to join")}
            </p>
          </form>
        )}

        {stage === "otp" && (
          <form onSubmit={submitOtp} className="w-full max-w-sm space-y-6" data-testid="otp-form">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-md bg-primary/10 border border-primary/30 flex items-center justify-center">
                <ShieldCheck size={18} className="text-primary" />
              </div>
              <div>
                <div className="label-mono">{t("التحقق", "Verification")}</div>
                <h2 className="text-2xl tracking-tight font-medium">{t("أدخل رمز الدخول", "Enter sign-in code")}</h2>
              </div>
            </div>
            <p className="text-sm text-muted-foreground">
              {emailSent
                ? t(`أرسلنا رمزًا من ٦ خانات إلى `, "We sent a 6-digit code to ")
                : t(`الإيميل غير مهيأ — اطلب الرمز من المسؤول. تم إنشاء طلب الدخول لـ `, "Email not configured — ask admin for the code. Sign-in request created for ")}
              <span className="font-medium text-foreground" dir="ltr">{email}</span>
            </p>
            <div>
              <label className="label-mono mb-1.5 block">{t("الرمز", "Code")}</label>
              <input
                data-testid="otp-code"
                type="text" inputMode="numeric" required value={otpCode}
                onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ""))}
                maxLength={6} dir="ltr"
                className="w-full px-3 py-3 bg-background border border-border rounded-md text-2xl font-mono tracking-[0.4em] text-center focus:outline-none focus:ring-2 focus:ring-primary"
                placeholder="000000"
              />
            </div>
            <button
              data-testid="otp-submit" type="submit" disabled={loading || otpCode.length < 4}
              className="w-full bg-primary text-primary-foreground py-2.5 rounded-md font-medium text-sm hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {loading ? t("جارٍ التحقق…", "Verifying…") : t("تأكيد", "Verify")}
            </button>
            <div className="flex items-center justify-between text-sm">
              <button type="button" onClick={() => setStage("credentials")} className="text-muted-foreground hover:text-foreground" data-testid="otp-back">
                {t("رجوع", "Back")}
              </button>
              <button type="button" onClick={resend} disabled={loading} className="text-primary hover:underline" data-testid="otp-resend">
                {t("أعد إرسال الرمز", "Resend code")}
              </button>
            </div>
          </form>
        )}

        {stage === "invite" && (
          <form onSubmit={submitInvite} className="w-full max-w-sm space-y-6" data-testid="invite-form">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-md bg-primary/10 border border-primary/30 flex items-center justify-center">
                <KeyRound size={18} className="text-primary" />
              </div>
              <div>
                <div className="label-mono">{t("قبول الدعوة", "Accept invite")}</div>
                <h2 className="text-2xl tracking-tight font-medium">{t("ادخل المنصة", "Enter the workspace")}</h2>
              </div>
            </div>
            <div className="flex items-center gap-2 text-sm border border-border bg-card rounded-md px-3 py-2">
              <Mail size={13} className="text-muted-foreground" />
              <span dir="ltr">{email}</span>
            </div>
            <div>
              <label className="label-mono mb-1.5 block">{t("كلمة المرور المؤقتة", "Temporary password")}</label>
              <input
                data-testid="invite-temp-pw"
                type="text" required value={tempPassword}
                onChange={(e) => setTempPassword(e.target.value)}
                dir="ltr" autoComplete="off"
                className="w-full px-3 py-2.5 bg-background border border-border rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary text-left"
                placeholder={t("من بريد الدعوة", "From invite email")}
              />
            </div>
            <button
              data-testid="invite-submit" type="submit" disabled={loading || !tempPassword}
              className="w-full bg-primary text-primary-foreground py-2.5 rounded-md font-medium text-sm hover:opacity-90 disabled:opacity-50"
            >
              {loading ? t("جارٍ القبول…", "Accepting…") : t("اقبل الدعوة", "Accept invite")}
            </button>
            <p className="label-mono text-[10px] text-muted-foreground">
              {t("ستُطلب منك تغيير كلمة المرور بعد الدخول", "You'll be asked to change your password after sign-in")}
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
