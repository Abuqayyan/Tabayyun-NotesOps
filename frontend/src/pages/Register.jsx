import { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { useLang } from "@/contexts/LanguageContext";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Languages } from "lucide-react";

export default function Register() {
  const { register } = useAuth();
  const { lang, toggle: toggleLang, t } = useLang();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await register(email, password, name);
      toast.success(t("تم إنشاء مساحة عملك", "Your workspace is ready"));
      navigate("/");
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("فشل إنشاء الحساب", "Account creation failed"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-8 relative">
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
      <form onSubmit={submit} className="w-full max-w-sm space-y-6" data-testid="register-form">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-primary flex items-center justify-center rounded-sm">
            <span className="text-primary-foreground font-mono font-bold text-sm">O</span>
          </div>
          <span className="font-medium tracking-tight">{t("أوبس‌كور", "OpsCore")}</span>
        </div>
        <div>
          <div className="label-mono">{t("إنشاء حساب", "Create account")}</div>
          <h2 className="text-2xl tracking-tight font-medium mt-1">{t("شغّل نظام تشغيلك", "Spin up your operating system")}</h2>
        </div>
        <div className="space-y-3">
          <div>
            <label className="label-mono mb-1.5 block">{t("الاسم", "Name")}</label>
            <input data-testid="register-name" required value={name} onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2.5 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary" />
          </div>
          <div>
            <label className="label-mono mb-1.5 block">{t("البريد الإلكتروني", "Email")}</label>
            <input data-testid="register-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
              dir="ltr"
              className="w-full px-3 py-2.5 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary text-left" />
          </div>
          <div>
            <label className="label-mono mb-1.5 block">{t("كلمة المرور", "Password")}</label>
            <input data-testid="register-password" type="password" required minLength={6} value={password} onChange={(e) => setPassword(e.target.value)}
              dir="ltr"
              className="w-full px-3 py-2.5 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary text-left" />
          </div>
        </div>
        <button data-testid="register-submit" type="submit" disabled={loading}
          className="w-full bg-primary text-primary-foreground py-2.5 rounded-md font-medium text-sm hover:opacity-90 disabled:opacity-50 flex items-center justify-center gap-2">
          {loading ? t("جارٍ الإنشاء…", "Creating…") : <>{t("أنشئ المساحة", "Create workspace")} <ArrowLeft size={14} className="rtl:rotate-180" /></>}
        </button>
        <div className="text-sm text-muted-foreground">
          {t("عندك حساب بالفعل؟", "Already have an account?")} <Link to="/login" className="text-primary hover:underline" data-testid="goto-login">{t("سجّل دخولك", "Sign in")}</Link>
        </div>
      </form>
    </div>
  );
}
