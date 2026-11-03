import styles from './styles/forgot-password.module.css';
import StepEmail from './steps/StepEmail';
import StepOTP from './steps/StepOTP';
import StepNewPassword from './steps/StepNewPassword';
import StepSuccess from './steps/StepSuccess';

const STEP_COUNT = 3;

/**
 * Шаги восстановления. fieldRef — основное поле текущего шага (email, первая
 * ячейка кода, новый пароль, кнопка на экране успеха): владелец ставит на него
 * фокус при смене шага.
 */
export default function ForgotPasswordStepper({
  state, onClose, emailLocked = false, fieldRef,
}) {
  const {
    step,
    email, setEmail,
    otp, setOtp,
    password, setPassword,
    password2, setPassword2,
    loading,
    errors, setErrors,
    timerSec,
    submitEmail,
    submitOtp,
    submitPassword,
    resendOtp,
    goBack,
  } = state;

  return (
    <>
      {step !== 'done' && (
        <>
          <div className={styles.stepper} aria-hidden="true">
            {Array.from({ length: STEP_COUNT }, (_, i) => {
              const n = i + 1;
              let cls = styles.dot;
              if (n === step) cls += ` ${styles.dotActive}`;
              else if (n < step) cls += ` ${styles.dotDone}`;
              return <div key={n} className={cls} />;
            })}
          </div>
          {/* Точки декоративные; прогресс для скринридера — текстом. */}
          <p className="visually-hidden">Шаг {step} из {STEP_COUNT}</p>
        </>
      )}

      {step === 1 && (
        <StepEmail
          email={email}
          setEmail={setEmail}
          errors={errors}
          setErrors={setErrors}
          loading={loading}
          readOnly={emailLocked}
          onSubmit={submitEmail}
          fieldRef={fieldRef}
        />
      )}

      {step === 2 && (
        <StepOTP
          email={email}
          otp={otp}
          setOtp={setOtp}
          errors={errors}
          setErrors={setErrors}
          loading={loading}
          timerSec={timerSec}
          onSubmit={submitOtp}
          onResend={resendOtp}
          onBack={() => goBack(1)}
          fieldRef={fieldRef}
        />
      )}

      {step === 3 && (
        <StepNewPassword
          email={email}
          password={password}
          setPassword={setPassword}
          password2={password2}
          setPassword2={setPassword2}
          errors={errors}
          setErrors={setErrors}
          loading={loading}
          onSubmit={submitPassword}
          onBack={() => goBack(2)}
          fieldRef={fieldRef}
        />
      )}

      {step === 'done' && (
        <StepSuccess onClose={onClose} fieldRef={fieldRef} />
      )}
    </>
  );
}
