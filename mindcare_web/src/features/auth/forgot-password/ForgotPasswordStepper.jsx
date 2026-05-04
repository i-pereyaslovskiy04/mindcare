import styles from './styles/forgot-password.module.css';
import StepEmail from './steps/StepEmail';
import StepOTP from './steps/StepOTP';
import StepNewPassword from './steps/StepNewPassword';
import StepSuccess from './steps/StepSuccess';

const STEP_COUNT = 3;

export default function ForgotPasswordStepper({ state, onClose }) {
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
        <div className={styles.stepper} aria-hidden="true">
          {Array.from({ length: STEP_COUNT }, (_, i) => {
            const n = i + 1;
            let cls = styles.dot;
            if (n === step) cls += ` ${styles.dotActive}`;
            else if (n < step) cls += ` ${styles.dotDone}`;
            return <div key={n} className={cls} />;
          })}
        </div>
      )}

      {step === 1 && (
        <StepEmail
          email={email}
          setEmail={setEmail}
          errors={errors}
          setErrors={setErrors}
          loading={loading}
          onSubmit={submitEmail}
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
        />
      )}

      {step === 3 && (
        <StepNewPassword
          password={password}
          setPassword={setPassword}
          password2={password2}
          setPassword2={setPassword2}
          errors={errors}
          setErrors={setErrors}
          loading={loading}
          onSubmit={submitPassword}
          onBack={() => goBack(2)}
        />
      )}

      {step === 'done' && (
        <StepSuccess onClose={onClose} />
      )}
    </>
  );
}
