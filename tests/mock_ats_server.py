import asyncio
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

mock_app = FastAPI(title="Mock ATS Test Server")


@mock_app.get("/greenhouse/acme/jobs/101", response_class=HTMLResponse)
async def greenhouse_job_page():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Greenhouse Careers - Acme Corp</title></head>
    <body>
        <h1>Software Engineer at Acme Corp</h1>
        <form id="application_form" action="/greenhouse/acme/jobs/101/submit" method="post" enctype="multipart/form-data">
            <div>
                <label for="first_name">First Name *</label>
                <input type="text" id="first_name" name="first_name" required />
            </div>
            <div>
                <label for="last_name">Last Name *</label>
                <input type="text" id="last_name" name="last_name" required />
            </div>
            <div>
                <label for="email">Email *</label>
                <input type="email" id="email" name="email" required />
            </div>
            <div>
                <label for="phone">Phone *</label>
                <input type="tel" id="phone" name="phone" />
            </div>
            <div>
                <label for="candidate_location">Location</label>
                <input type="text" id="candidate_location" name="candidate_location" />
            </div>
            <div>
                <label for="job_application_answers_attributes_0_text_value">LinkedIn Profile</label>
                <input type="url" name="job_application[answers_attributes][0][text_value]" placeholder="https://linkedin.com/in/..." />
            </div>
            <div>
                <label for="resume">Resume/CV *</label>
                <input type="file" id="resume" name="resume" required />
            </div>
            <div>
                <label>Preferred Work Arrangement</label>
                <input type="text" placeholder="Remote or On-site" />
            </div>
            <div>
                <label>Years of Python Experience</label>
                <input type="text" placeholder="Years" />
            </div>
            <div>
                <input type="checkbox" id="consent" name="consent" required />
                <label for="consent">I agree to the privacy policy</label>
            </div>
            <button type="submit" id="submit_app">Submit Application</button>
        </form>
    </body>
    </html>
    """


@mock_app.post("/greenhouse/acme/jobs/101/submit")
async def greenhouse_submit(request: Request):
    return RedirectResponse(url="/greenhouse/confirmation", status_code=303)


@mock_app.get("/greenhouse/confirmation", response_class=HTMLResponse)
async def greenhouse_confirmation():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Application Submitted</title></head>
    <body>
        <div id="application_confirmation">
            <h1>Thank you for applying</h1>
            <p>Your application was successfully submitted. We will contact you if there are next steps.</p>
        </div>
    </body>
    </html>
    """


@mock_app.get("/lever/acme/202", response_class=HTMLResponse)
async def lever_job_page():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Lever - Acme Posting</title></head>
    <body>
        <h1>Backend Engineer at Acme</h1>
        <form id="lever-form" action="/lever/acme/202/submit" method="post" enctype="multipart/form-data">
            <input type="text" name="name" placeholder="Full name" required />
            <input type="email" name="email" placeholder="Email" required />
            <input type="tel" name="phone" placeholder="Phone" />
            <input type="text" name="org" placeholder="Current company" />
            <input type="url" name="urls[LinkedIn]" placeholder="LinkedIn URL" />
            <input type="file" name="resume" />
            <button type="submit" id="btn-submit">Submit application</button>
        </form>
    </body>
    </html>
    """


@mock_app.post("/lever/acme/202/submit", response_class=HTMLResponse)
async def lever_submit(request: Request):
    return """
    <!DOCTYPE html>
    <html>
    <body>
        <div class="lever-confirmation">
            <h3>Application submitted</h3>
            <p>Thank you! We have received your application.</p>
        </div>
    </body>
    </html>
    """


@mock_app.get("/ashby/acme/job/303", response_class=HTMLResponse)
async def ashby_job_page():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Ashby Job - Software Engineer</title></head>
    <body>
        <h1>Software Engineer at Ashby Acme</h1>
        <button onclick="window.location.href='/ashby/acme/job/303/application'">Apply for this Job</button>
    </body>
    </html>
    """


@mock_app.get("/ashby/acme/job/303/application", response_class=HTMLResponse)
async def ashby_application_page():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Ashby Application</title></head>
    <body>
        <form id="_application_form" action="/ashby/acme/job/303/submit" method="post" enctype="multipart/form-data">
            <input type="text" id="_systemfield_name" name="_systemfield_name" placeholder="Your Name" required />
            <input type="email" id="_systemfield_email" name="_systemfield_email" placeholder="Your Email" required />
            <div data-field-path="_systemfield_location">
                <input type="text" role="combobox" placeholder="Location" />
            </div>
            <input type="file" id="_systemfield_resume" name="_systemfield_resume" required />
            <div class="screening-question">
                <p>Are you authorized to work in India?</p>
                <button type="button" data-option="yes" onclick="this.classList.add('selected')">Yes</button>
                <button type="button" data-option="no">No</button>
            </div>
            <button type="submit">Submit Application</button>
        </form>
    </body>
    </html>
    """


@mock_app.post("/ashby/acme/job/303/submit", response_class=HTMLResponse)
async def ashby_submit(request: Request):
    return """
    <!DOCTYPE html>
    <html>
    <body>
        <div class="ashby-application-submitted-page">
            <h1>Thank you for applying</h1>
            <p>Your application was successfully submitted.</p>
        </div>
    </body>
    </html>
    """


@mock_app.get("/mock/multi-step", response_class=HTMLResponse)
async def multi_step_page():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Multi-Step Application</title></head>
    <body>
        <form id="multistep_form" action="/greenhouse/confirmation" method="get">
            <div id="step1">
                <h2>Step 1: Contact</h2>
                <input type="text" name="name" placeholder="Full Name" value="Abhishek Yadav" />
                <input type="email" name="email" placeholder="Email" value="abhishek@example.com" />
                <button type="button" id="next1" onclick="document.getElementById('step1').style.display='none'; document.getElementById('step2').style.display='block';">Next Step</button>
            </div>
            <div id="step2" style="display:none;">
                <h2>Step 2: Experience</h2>
                <input type="text" placeholder="Years of Java Experience" value="2" />
                <button type="button" id="next2" onclick="document.getElementById('step2').style.display='none'; document.getElementById('step3').style.display='block';">Next Step</button>
            </div>
            <div id="step3" style="display:none;">
                <h2>Step 3: Review and Submit</h2>
                <input type="file" name="resume" />
                <button type="submit" id="final_submit">Submit Application</button>
            </div>
        </form>
    </body>
    </html>
    """


@mock_app.get("/mock/slow-submit", response_class=HTMLResponse)
async def slow_submit_page():
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Slow ATS Gateway</title></head>
    <body>
        <form id="slow_form" onsubmit="event.preventDefault(); document.getElementById('loader').style.display='block'; setTimeout(() => { document.body.innerHTML = '<h1>Thank you for applying</h1><p>Your application was successfully submitted.</p>'; }, 7000);">
            <input type="text" name="name" value="Abhishek Yadav" />
            <input type="email" name="email" value="abhishek@example.com" />
            <button type="submit" id="slow_submit_btn">Submit Application</button>
        </form>
        <div id="loader" style="display:none;">Uploading files... Processing submission (7 seconds)...</div>
    </body>
    </html>
    """


@mock_app.get("/mock/validation-error", response_class=HTMLResponse)
async def validation_error_page():
    return """
    <!DOCTYPE html>
    <html>
    <body>
        <form id="invalid_form" onsubmit="event.preventDefault(); document.getElementById('err_banner').style.display='block';">
            <input type="text" name="name" />
            <div id="err_banner" class="field-error" style="display:none;">
                Please enter a valid phone number.
            </div>
            <button type="submit" id="err_submit_btn">Submit Application</button>
        </form>
    </body>
    </html>
    """


@mock_app.get("/mock/captcha", response_class=HTMLResponse)
async def captcha_page():
    return """
    <!DOCTYPE html>
    <html>
    <body>
        <form id="captcha_form">
            <input type="text" name="name" value="Abhishek Yadav" />
            <iframe src="https://www.google.com/recaptcha/api2/anchor" title="reCAPTCHA challenge"></iframe>
            <button type="submit">Submit Application</button>
        </form>
    </body>
    </html>
    """
