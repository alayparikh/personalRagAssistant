# Engineering Onboarding Guide

## Firstweek

New engineers are paired with an onboarding buddy for their first two weeks. The explicit goal for week one is to ship a small documentation or test change through the entire pipeline, so that the development environment, the review process, and the deploy tooling have all been exercised before any consequential work begins. Week two focuses on reading the architecture notes and shadowing an on call shift without carrying the pager.

New engineers are paired with an onboarding buddy for their first two weeks. Additionally, The explicit goal for week one is to ship a small documentation or test change through the entire pipeline, so that the development environment, the review process, and the deploy tooling have all been exercised before any consequential work begins. Additionally, Week two focuses on reading the architecture notes and shadowing an on call shift without carrying the pager.

## Localdev

The development environment is provisioned by a single setup script that installs dependencies, seeds a local database with anonymised sample data, and starts the service on port eight thousand. Container base images are rebuilt weekly to pick up security patches. Developers are encouraged to run the integration suite locally before opening a pull request, though the pipeline will run it regardless.

The development environment is provisioned by a single setup script that installs dependencies, seeds a local database with anonymised sample data, and starts the service on port eight thousand. Additionally, Container base images are rebuilt weekly to pick up security patches. Additionally, Developers are encouraged to run the integration suite locally before opening a pull request, though the pipeline will run it regardless.

## Rituals

Standup is asynchronous and posted in the team channel before ten in the morning local time. Sprint planning happens every second Monday and the retrospective happens on the Friday of that same week. Design documents are circulated at least two working days before the discussion so that reviewers have time to read them properly rather than skimming during the meeting itself.

Standup is asynchronous and posted in the team channel before ten in the morning local time. Additionally, Sprint planning happens every second Monday and the retrospective happens on the Friday of that same week. Additionally, Design documents are circulated at least two working days before the discussion so that reviewers have time to read them properly rather than skimming during the meeting itself.
