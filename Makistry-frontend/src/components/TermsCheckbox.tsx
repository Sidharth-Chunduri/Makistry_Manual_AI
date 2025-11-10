interface Props {
  agreed: boolean;
  onToggle: () => void;
}

export function TermsCheckbox({ agreed, onToggle }: Props) {
  return (
    <label className="flex items-start gap-2 text-xs text-gray-700">
      <input type="checkbox" checked={agreed} onChange={onToggle} />
      <span>
        I agree to the{" "}
        <a href="https://makistry.com/terms-of-service" target="_blank"
           className="underline hover:text-primary">
          Terms of Service
        </a>{" "}
        and{" "}
        <a href="https://makistry.com/privacy-policy" target="_blank"
           className="underline hover:text-primary">
          Privacy Policy
        </a>.
      </span>
    </label>
  );
}