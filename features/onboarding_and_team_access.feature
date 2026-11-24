@onboarding @rbac
Feature: Post-Signup Onboarding Demo, Managed Books Tier, and Server-Side Team RBAC
  As a newly onboarded UAE SME founder using Lumen Accounting Suite
  I want to complete my company setup tour, preview Managed Books pricing, and restrict read-only team viewers
  So that new users orient quickly and unauthorized mutations are rejected server-side

  Scenario: Managed Books signup transitions from Settings onboarding to Lumy AI welcome and interactive demo
    When an unauthenticated visitor opens the application root
    Then the browser should redirect to the "/welcome" entrypoint
    And the Managed Books welcome tier should display "1,450" AED with "Free Setup"
    When the visitor starts onboarding registration for company "Lumen Managed Onboarding" with password "Lumen2026" on the "managed" plan
    Then the application should display the Settings onboarding banner for the registered company
    When the founder saves company details in Settings onboarding
    Then the Lumy AI welcome dialog should greet the registered company on the Dashboard
    When the founder launches and advances the interactive product demo
    Then the interactive product demo should dismiss cleanly after Step 2

  Scenario: Read-only team viewer is blocked on UI and receives HTTP 403 on server state mutations
    When an unauthenticated visitor opens the application root
    Then the browser should redirect to the "/welcome" entrypoint
    When the visitor registers company "Lumen Team RBAC Co" with password "Lumen2026" on the "advance" plan
    And the user navigates to the "Settings" view
    And the admin invites a "viewer" teammate named "Tariq Viewer" with password "ViewerPass123"
    And the user signs out from the application topbar
    And the invited viewer signs in on the Welcome page
    Then the workspace should reflect role "viewer" and reject POST /api/v1/state with HTTP 403
