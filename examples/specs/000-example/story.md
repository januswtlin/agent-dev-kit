# 000 Pay by bank transfer with proof of payment

*繁體中文：[story-zh-TW.md](story-zh-TW.md). This English version governs if the two differ.*

> Original requirement: 使用者可以透過轉帳付款並且附上轉帳憑證，商店負責人檢視憑證後給予 pass。

## Story

As a customer, I want to pay by bank transfer and upload proof of the transfer, so that I can complete an order without online payment.
As a shop owner, I want to look at the proof and then pass or reject it, so that I only ship once the money has really arrived.

## Acceptance criteria

- **AC-000-1** WHEN a customer chooses bank transfer for an order awaiting payment and uploads one proof THEN the order moves to awaiting review.
- **AC-000-2** WHEN the shop owner views the proof and marks it passed THEN the order becomes paid.
- **AC-000-3** WHEN the shop owner rejects the proof with a reason THEN the order returns to awaiting payment and the customer can upload again.
- **AC-000-4** Only the owner of that shop can view and review the proof.

## Test cases

| ID | AC | Level | Description |
|---|---|---|---|
| TC-000-01 | AC-000-1 | integration | Uploading a proof to an order awaiting payment moves it to awaiting review |
| TC-000-02 | AC-000-1 | unit | A file that is not an image or PDF, or is over 10 MB, is refused and the order does not change |
| TC-000-03 | AC-000-2 | integration | After the owner passes it, the order is paid and the reviewer and time are recorded |
| TC-000-04 | AC-000-3 | integration | Rejecting needs a reason; afterwards the order awaits payment and the customer can upload again |
| TC-000-05 | AC-000-4 | integration | Another shop's owner and an ordinary customer are refused when they try to view the proof |
| TC-000-06 | AC-000-2 | unit | An order that is already paid cannot be reviewed again |

## Done when

- [ ] Every TC passes in CI
- [ ] Deployed to staging
- [ ] The owner has walked through one pass and one rejection on staging (manual)

## Clarifications

- Q: What state is the order in after a rejection? A: Back to awaiting payment; the customer may upload again, with no limit.
- Q: Who decides when the amount does not match? A: The owner, by eye. The system does not compare amounts.
- Q: Can a pass be undone? A: Not in this story. A separate story.

## Assumptions

- An order has one valid proof at a time; a new upload replaces the previous one.
- Proofs may be JPG, PNG or PDF, up to 10 MB.
- The customer gets an in-app notice on pass or rejection. No email.

## Out of scope

- Automatic reconciliation or bank API integration.
- Undoing a passed payment, or refunds.
